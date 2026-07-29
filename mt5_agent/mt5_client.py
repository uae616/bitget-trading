from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .config import MT5Config

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover
    mt5 = None


class MT5Client:
    def __init__(self, config: MT5Config) -> None:
        self.config = config
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def _require_mt5(self) -> None:
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not installed")

    def connect(self) -> bool:
        self._require_mt5()

        init_kwargs = {
            "path": self.config.path,
            "login": self.config.login,
            "server": self.config.server,
            "timeout": self.config.timeout_ms,
        }
        init_kwargs["password"] = self.config.secret
        initialize_ok = mt5.initialize(**init_kwargs)
        if not initialize_ok:
            self._connected = False
            return False
        self._connected = True
        return True

    def shutdown(self) -> None:
        if mt5 is not None:
            mt5.shutdown()
        self._connected = False

    def health_check(self) -> bool:
        if mt5 is None or not self._connected:
            return False
        info = mt5.terminal_info()
        return bool(info and info.connected)

    def reconnect(self) -> bool:
        self.shutdown()
        return self.connect()

    def symbols_get(self) -> list[Any]:
        self._require_mt5()
        return list(mt5.symbols_get() or [])

    def symbol_info(self, symbol: str) -> Any:
        self._require_mt5()
        return mt5.symbol_info(symbol)

    def symbol_info_tick(self, symbol: str) -> Any:
        self._require_mt5()
        return mt5.symbol_info_tick(symbol)

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int) -> Any:
        self._require_mt5()
        return mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count)

    def market_book_add(self, symbol: str) -> bool:
        self._require_mt5()
        return bool(mt5.market_book_add(symbol))

    def market_book_get(self, symbol: str) -> Any:
        self._require_mt5()
        return mt5.market_book_get(symbol)

    def order_check(self, request: dict[str, Any]) -> Any:
        self._require_mt5()
        return mt5.order_check(request)

    def order_send(self, request: dict[str, Any]) -> Any:
        self._require_mt5()
        return mt5.order_send(request)

    def account_info(self) -> Any:
        self._require_mt5()
        return mt5.account_info()

    def as_dict(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if hasattr(value, "_asdict"):
            return value._asdict()
        if hasattr(value, "__dataclass_fields__"):
            return asdict(value)
        return dict(value)
