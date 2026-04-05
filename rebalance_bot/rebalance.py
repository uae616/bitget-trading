"""
Core rebalancing logic.

The rebalancer is intentionally decoupled from the Bitget client so that it
can be unit-tested without network access.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thin protocol so the rebalancer can be tested with a mock client
# ---------------------------------------------------------------------------

class TradingClient(Protocol):
    def get_spot_balances(self) -> dict[str, float]: ...
    def get_price(self, symbol: str) -> float | None: ...
    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        quote_qty: float | None = None,
    ) -> dict: ...


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PortfolioSnapshot:
    """Current state of the portfolio at a single point in time."""

    # coin -> balance in that coin's native units
    balances: dict[str, float]
    # coin -> price in quote currency (e.g. USDT)
    prices: dict[str, float]

    @property
    def values(self) -> dict[str, float]:
        """coin -> value denominated in quote currency."""
        return {
            coin: bal * self.prices.get(coin, 1.0)
            for coin, bal in self.balances.items()
        }

    @property
    def total_value(self) -> float:
        return sum(self.values.values())

    @property
    def weights(self) -> dict[str, float]:
        """coin -> actual portfolio weight [0, 1]."""
        total = self.total_value
        if total == 0:
            return {coin: 0.0 for coin in self.balances}
        return {coin: val / total for coin, val in self.values.items()}


@dataclass
class RebalanceOrder:
    """Represents a single rebalancing trade to be executed."""

    coin: str
    side: str           # "buy" or "sell"
    symbol: str         # e.g. "BTCUSDT"
    quantity: float     # base-asset units (used for sell)
    quote_qty: float    # quote-asset units (used for buy)

    def __repr__(self) -> str:
        if self.side == "buy":
            return f"BUY  {self.coin}: {self.quote_qty:.2f} USDT"
        return f"SELL {self.coin}: {self.quantity:.8f} (≈ {self.quote_qty:.2f} USDT)"


# ---------------------------------------------------------------------------
# Main rebalancer
# ---------------------------------------------------------------------------

class Rebalancer:
    """Computes and executes the trades needed to reach target allocations."""

    def __init__(
        self,
        client: TradingClient,
        target_allocations: dict[str, float] | None = None,
        threshold: float = config.REBALANCE_THRESHOLD,
        quote_currency: str = config.QUOTE_CURRENCY,
        min_order_size: float = config.MIN_ORDER_SIZE_QUOTE,
        dry_run: bool = False,
    ) -> None:
        self._client = client
        self._targets = target_allocations or config.TARGET_ALLOCATIONS
        self._threshold = threshold
        self._quote = quote_currency
        self._min_order = min_order_size
        self._dry_run = dry_run

        self._validate_targets()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> list[RebalanceOrder]:
        """Fetch portfolio state, compute and (unless dry-run) execute orders.

        Returns the list of orders that were generated (executed or simulated).
        """
        snapshot = self._build_snapshot()

        if snapshot.total_value == 0:
            logger.warning("Portfolio total value is zero; nothing to rebalance.")
            return []

        orders = self.compute_orders(snapshot)

        if not orders:
            logger.info("Portfolio is within threshold; no rebalancing needed.")
            return []

        for order in orders:
            logger.info("Order: %s", order)
            if not self._dry_run:
                self._execute(order)

        return orders

    def compute_orders(self, snapshot: PortfolioSnapshot) -> list[RebalanceOrder]:
        """Pure function: compute rebalancing orders for the given snapshot.

        This method does *not* touch the exchange and is safe to test in
        isolation.
        """
        orders: list[RebalanceOrder] = []
        total = snapshot.total_value
        current_weights = snapshot.weights

        for coin, target_weight in self._targets.items():
            current_weight = current_weights.get(coin, 0.0)
            drift = current_weight - target_weight

            if abs(drift) < self._threshold:
                logger.debug(
                    "%s drift %.2f%% is within threshold; skipping.",
                    coin,
                    drift * 100,
                )
                continue

            # Quote value we need to move
            delta_quote = abs(drift) * total

            if delta_quote < self._min_order:
                logger.debug(
                    "%s delta %.2f %s is below min order size; skipping.",
                    coin,
                    delta_quote,
                    self._quote,
                )
                continue

            if coin == self._quote:
                # Quote currency does not trade against itself.
                continue

            symbol = f"{coin}{self._quote}"
            price = snapshot.prices.get(coin)
            if price is None or price == 0:
                logger.warning("No price for %s; skipping.", coin)
                continue

            base_qty = delta_quote / price

            if drift > 0:
                # Over-weight → sell
                orders.append(
                    RebalanceOrder(
                        coin=coin,
                        side="sell",
                        symbol=symbol,
                        quantity=base_qty,
                        quote_qty=delta_quote,
                    )
                )
            else:
                # Under-weight → buy
                orders.append(
                    RebalanceOrder(
                        coin=coin,
                        side="buy",
                        symbol=symbol,
                        quantity=base_qty,
                        quote_qty=delta_quote,
                    )
                )

        return orders

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_snapshot(self) -> PortfolioSnapshot:
        balances = self._client.get_spot_balances()

        # Ensure every target coin is present (with 0 balance if absent)
        for coin in self._targets:
            balances.setdefault(coin, 0.0)

        prices: dict[str, float] = {}
        for coin in balances:
            if coin == self._quote:
                prices[coin] = 1.0
            else:
                symbol = f"{coin}{self._quote}"
                price = self._client.get_price(symbol)
                if price is not None:
                    prices[coin] = price
                else:
                    logger.warning("Could not fetch price for %s; excluding.", symbol)

        # Remove coins for which we have no price (except quote currency)
        balances = {
            coin: bal
            for coin, bal in balances.items()
            if coin in prices
        }

        return PortfolioSnapshot(balances=balances, prices=prices)

    def _execute(self, order: RebalanceOrder) -> None:
        try:
            result = self._client.place_market_order(
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                quote_qty=order.quote_qty if order.side == "buy" else None,
            )
            logger.info("Order placed: %s → %s", order, result)
        except Exception as exc:
            logger.error("Failed to place order %s: %s", order, exc)

    def _validate_targets(self) -> None:
        total = sum(self._targets.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"TARGET_ALLOCATIONS must sum to 1.0; got {total:.6f}"
            )
        for coin, weight in self._targets.items():
            if weight < 0:
                raise ValueError(
                    f"Allocation for {coin} must be >= 0; got {weight}"
                )
