from __future__ import annotations


def place_order_mt5(mt5, symbol: str, direction: str, lots: float, sl: float | None = None, tp: float | None = None) -> dict:
    """
    Scaffold for MT5 order placement.
    Replace request fields with broker-specific constraints as needed.
    """
    if direction not in {"BUY", "SELL"} or lots <= 0:
        return {"ok": False, "error": "invalid_order_request"}

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"ok": False, "error": f"no_tick:{symbol}"}

    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if direction == "BUY" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lots),
        "type": order_type,
        "price": price,
        "deviation": 20,
        "magic": 4686001,
        "comment": "mt5_scalper_scaffold",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    if sl is not None:
        request["sl"] = float(sl)
    if tp is not None:
        request["tp"] = float(tp)

    result = mt5.order_send(request)
    if result is None:
        return {"ok": False, "error": "order_send_none"}
    retcode = int(getattr(result, "retcode", 0) or 0)
    ok = retcode == getattr(mt5, "TRADE_RETCODE_DONE", -1)
    return {"ok": ok, "retcode": retcode, "result": str(result)}
