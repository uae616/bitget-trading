from __future__ import annotations

from datetime import datetime, timezone

from .mt5_client import MT5Client
from .types import MarketSnapshot


class MarketDataAdapter:
    def __init__(self, client: MT5Client) -> None:
        self.client = client

    def ensure_symbol(self, symbol: str) -> bool:
        info = self.client.symbol_info(symbol)
        if info is None:
            return False
        return bool(getattr(info, "visible", True))

    def get_snapshot(self, symbol: str) -> MarketSnapshot:
        tick = self.client.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"No tick data for symbol {symbol}")

        bid = float(tick.bid)
        ask = float(tick.ask)
        spread = ask - bid
        return MarketSnapshot(
            symbol=symbol,
            bid=bid,
            ask=ask,
            spread=spread,
            timestamp=datetime.now(timezone.utc),
            features={"last": float(getattr(tick, "last", ask)), "volume": float(getattr(tick, "volume", 0.0))},
        )

    def get_recent_candles(self, symbol: str, timeframe: int, count: int = 100):
        rates = self.client.copy_rates_from_pos(symbol, timeframe, 0, count)
        return [] if rates is None else list(rates)

    def get_order_book(self, symbol: str):
        self.client.market_book_add(symbol)
        book = self.client.market_book_get(symbol)
        return [] if book is None else list(book)
