from __future__ import annotations

from typing import Any

from .mt5_client import MT5Client
from .types import TradeRequest


class TradeRequestValidator:
    def __init__(self, client: MT5Client) -> None:
        self.client = client

    def validate(self, request: TradeRequest) -> None:
        info = self.client.symbol_info(request.symbol)
        if info is None:
            raise ValueError(f"Unknown symbol: {request.symbol}")
        if not getattr(info, "trade_mode", 0):
            raise ValueError(f"Symbol not tradable: {request.symbol}")

        min_volume = float(getattr(info, "volume_min", 0.0))
        max_volume = float(getattr(info, "volume_max", 0.0))
        step = float(getattr(info, "volume_step", 0.0))
        if request.volume < min_volume or (max_volume > 0 and request.volume > max_volume):
            raise ValueError("Volume outside symbol limits")
        if step > 0:
            ratio = request.volume / step
            if abs(ratio - round(ratio)) > 1e-8:
                raise ValueError("Volume does not match symbol step")

        digits = int(getattr(info, "digits", 5))
        if round(request.price, digits) != request.price:
            raise ValueError("Price precision does not match symbol digits")

        stops_level_points = int(getattr(info, "trade_stops_level", 0))
        point = float(getattr(info, "point", 0.0))
        min_stop_distance = stops_level_points * point

        if request.stop_loss is not None and abs(request.price - request.stop_loss) < min_stop_distance:
            raise ValueError("Stop-loss too close to entry")
        if request.take_profit is not None and abs(request.price - request.take_profit) < min_stop_distance:
            raise ValueError("Take-profit too close to entry")

        check_request = _to_mt5_request(request)
        check = self.client.order_check(check_request)
        if check is None:
            raise ValueError("Margin check failed: no response")

        retcode = int(getattr(check, "retcode", 0))
        if retcode != 0:
            raise ValueError(f"Margin/order check failed with retcode={retcode}")


def _to_mt5_request(request: TradeRequest) -> dict[str, Any]:
    from MetaTrader5 import ORDER_TYPE_BUY, ORDER_TYPE_SELL, TRADE_ACTION_DEAL

    side = request.side.lower()
    order_type = ORDER_TYPE_BUY if side == "buy" else ORDER_TYPE_SELL
    payload = {
        "action": TRADE_ACTION_DEAL,
        "symbol": request.symbol,
        "volume": request.volume,
        "type": order_type,
        "price": request.price,
        "deviation": request.deviation,
        "magic": request.magic,
        "comment": request.comment,
    }
    if request.stop_loss is not None:
        payload["sl"] = request.stop_loss
    if request.take_profit is not None:
        payload["tp"] = request.take_profit
    return payload
