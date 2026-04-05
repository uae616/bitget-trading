"""Unit tests for the rebalancing logic (no network access required)."""

import sys
import os

# Ensure the rebalance_bot package is importable when running pytest from the
# repository root or from within the rebalance_bot directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from rebalance import PortfolioSnapshot, Rebalancer, RebalanceOrder


# ---------------------------------------------------------------------------
# Minimal mock client
# ---------------------------------------------------------------------------

class MockClient:
    """Fake trading client with controllable responses."""

    def __init__(self, balances: dict, prices: dict):
        self._balances = balances
        self._prices = prices
        self.orders_placed: list[dict] = []

    def get_spot_balances(self) -> dict:
        return dict(self._balances)

    def get_price(self, symbol: str) -> float | None:
        # symbol is e.g. "BTCUSDT"; extract the base coin
        for coin, price in self._prices.items():
            if symbol.startswith(coin):
                return price
        return None

    def place_market_order(self, symbol, side, quantity, quote_qty=None) -> dict:
        record = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "quote_qty": quote_qty,
        }
        self.orders_placed.append(record)
        return {"orderId": "mock-123"}


# ---------------------------------------------------------------------------
# PortfolioSnapshot tests
# ---------------------------------------------------------------------------

class TestPortfolioSnapshot:
    def test_values_uses_prices(self):
        snap = PortfolioSnapshot(
            balances={"BTC": 1.0, "USDT": 1000.0},
            prices={"BTC": 50000.0, "USDT": 1.0},
        )
        assert snap.values["BTC"] == pytest.approx(50000.0)
        assert snap.values["USDT"] == pytest.approx(1000.0)

    def test_total_value(self):
        snap = PortfolioSnapshot(
            balances={"BTC": 1.0, "USDT": 1000.0},
            prices={"BTC": 50000.0, "USDT": 1.0},
        )
        assert snap.total_value == pytest.approx(51000.0)

    def test_weights_sum_to_one(self):
        snap = PortfolioSnapshot(
            balances={"BTC": 1.0, "ETH": 10.0, "USDT": 500.0},
            prices={"BTC": 10000.0, "ETH": 500.0, "USDT": 1.0},
        )
        assert sum(snap.weights.values()) == pytest.approx(1.0)

    def test_weights_zero_total(self):
        snap = PortfolioSnapshot(balances={"BTC": 0.0}, prices={"BTC": 10000.0})
        assert snap.weights["BTC"] == 0.0


# ---------------------------------------------------------------------------
# Rebalancer.compute_orders tests
# ---------------------------------------------------------------------------

def make_rebalancer(client, targets, threshold=0.05, min_order=10.0, dry_run=True):
    return Rebalancer(
        client=client,
        target_allocations=targets,
        threshold=threshold,
        quote_currency="USDT",
        min_order_size=min_order,
        dry_run=dry_run,
    )


class TestComputeOrders:
    def _snap(self, balances, prices):
        return PortfolioSnapshot(balances=balances, prices=prices)

    def test_balanced_portfolio_no_orders(self):
        """When current weights match targets exactly, no orders are generated."""
        targets = {"BTC": 0.5, "ETH": 0.3, "USDT": 0.2}
        client = MockClient({}, {})
        r = make_rebalancer(client, targets)

        snap = self._snap(
            balances={"BTC": 1.0, "ETH": 6.0, "USDT": 2000.0},
            prices={"BTC": 5000.0, "ETH": 500.0, "USDT": 1.0},
        )
        # Total = 5000 + 3000 + 2000 = 10000; weights = 0.5, 0.3, 0.2
        orders = r.compute_orders(snap)
        assert orders == []

    def test_overweight_coin_generates_sell(self):
        """An over-weight coin should produce a SELL order."""
        # BTC target 0.5, but portfolio is all BTC → drift 0.5 > threshold 0.05
        targets = {"BTC": 0.5, "USDT": 0.5}
        client = MockClient({}, {})
        r = make_rebalancer(client, targets, threshold=0.05)

        snap = self._snap(
            balances={"BTC": 1.0, "USDT": 0.0},
            prices={"BTC": 10000.0, "USDT": 1.0},
        )
        orders = r.compute_orders(snap)
        sell_orders = [o for o in orders if o.side == "sell" and o.coin == "BTC"]
        assert len(sell_orders) == 1

    def test_underweight_coin_generates_buy(self):
        """An under-weight coin should produce a BUY order."""
        # ETH target 0.5, but portfolio has only USDT → buy ETH
        targets = {"ETH": 0.5, "USDT": 0.5}
        client = MockClient({}, {})
        r = make_rebalancer(client, targets, threshold=0.05)

        snap = self._snap(
            balances={"ETH": 0.0, "USDT": 10000.0},
            prices={"ETH": 1000.0, "USDT": 1.0},
        )
        orders = r.compute_orders(snap)
        buy_orders = [o for o in orders if o.side == "buy" and o.coin == "ETH"]
        assert len(buy_orders) == 1
        assert buy_orders[0].quote_qty == pytest.approx(5000.0)

    def test_drift_below_threshold_no_order(self):
        """Drift below threshold must not trigger an order."""
        targets = {"BTC": 0.50, "USDT": 0.50}
        client = MockClient({}, {})
        r = make_rebalancer(client, targets, threshold=0.10)

        # BTC weight = 0.52, drift = 0.02 < threshold 0.10
        snap = self._snap(
            balances={"BTC": 1.0, "USDT": 9600.0},
            prices={"BTC": 10400.0, "USDT": 1.0},
        )
        orders = r.compute_orders(snap)
        assert orders == []

    def test_order_below_min_size_skipped(self):
        """Orders smaller than min_order_size should be skipped."""
        targets = {"BTC": 0.50, "USDT": 0.50}
        client = MockClient({}, {})
        r = make_rebalancer(client, targets, threshold=0.05, min_order=1000.0)

        # Total value 100 USDT; drift ≈ 0.1 → delta 10 USDT < min 1000
        snap = self._snap(
            balances={"BTC": 0.004, "USDT": 46.0},
            prices={"BTC": 10000.0, "USDT": 1.0},
        )
        orders = r.compute_orders(snap)
        assert orders == []

    def test_quote_currency_not_traded(self):
        """The quote currency itself should never appear in an order."""
        targets = {"BTC": 0.50, "USDT": 0.50}
        client = MockClient({}, {})
        r = make_rebalancer(client, targets, threshold=0.05)

        # USDT is the quote – even though it is underweight it must not be traded
        snap = self._snap(
            balances={"BTC": 1.0, "USDT": 0.0},
            prices={"BTC": 10000.0, "USDT": 1.0},
        )
        orders = r.compute_orders(snap)
        assert all(o.coin != "USDT" for o in orders)

    def test_sell_order_quantity(self):
        """Sell quantity (base asset) should equal delta_quote / price."""
        targets = {"BTC": 0.5, "USDT": 0.5}
        client = MockClient({}, {})
        r = make_rebalancer(client, targets, threshold=0.05)

        # BTC weight 1.0; target 0.5; drift 0.5; total 10000
        # delta_quote = 0.5 * 10000 = 5000; base_qty = 5000 / 10000 = 0.5
        snap = self._snap(
            balances={"BTC": 1.0, "USDT": 0.0},
            prices={"BTC": 10000.0, "USDT": 1.0},
        )
        orders = r.compute_orders(snap)
        sell = next(o for o in orders if o.side == "sell")
        assert sell.quantity == pytest.approx(0.5)
        assert sell.quote_qty == pytest.approx(5000.0)


# ---------------------------------------------------------------------------
# Rebalancer validation tests
# ---------------------------------------------------------------------------

class TestRebalancerValidation:
    def test_targets_not_summing_to_one_raises(self):
        client = MockClient({}, {})
        with pytest.raises(ValueError, match="must sum to 1.0"):
            Rebalancer(
                client=client,
                target_allocations={"BTC": 0.4, "ETH": 0.3},  # sums to 0.7
            )

    def test_negative_allocation_raises(self):
        client = MockClient({}, {})
        with pytest.raises(ValueError, match=">= 0"):
            Rebalancer(
                client=client,
                target_allocations={"BTC": -0.1, "USDT": 1.1},
            )


# ---------------------------------------------------------------------------
# Rebalancer.run integration (with mock client)
# ---------------------------------------------------------------------------

class TestRebalancerRun:
    def test_dry_run_does_not_place_orders(self):
        """In dry-run mode no orders should reach the exchange."""
        targets = {"BTC": 0.5, "USDT": 0.5}
        balances = {"BTC": 1.0, "USDT": 0.0}
        prices = {"BTC": 10000.0}

        client = MockClient(balances, prices)
        r = make_rebalancer(client, targets, dry_run=True)
        r.run()

        assert client.orders_placed == []

    def test_live_run_places_orders(self):
        """In live mode orders should be sent to the exchange."""
        targets = {"BTC": 0.5, "USDT": 0.5}
        balances = {"BTC": 1.0, "USDT": 0.0}
        prices = {"BTC": 10000.0}

        client = MockClient(balances, prices)
        r = make_rebalancer(client, targets, dry_run=False)
        orders = r.run()

        assert len(orders) > 0
        assert len(client.orders_placed) == len(orders)

    def test_zero_portfolio_returns_no_orders(self):
        """Empty portfolio should not generate any orders."""
        targets = {"BTC": 0.5, "USDT": 0.5}
        client = MockClient({"BTC": 0.0, "USDT": 0.0}, {"BTC": 10000.0})
        r = make_rebalancer(client, targets)
        orders = r.run()
        assert orders == []
