from __future__ import annotations

from typing import Any


def to_mt5_request(request: Any) -> dict[str, Any]:
    from MetaTrader5 import ORDER_TYPE_BUY, ORDER_TYPE_SELL, TRADE_ACTION_DEAL

    side = str(request.side).lower()
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
