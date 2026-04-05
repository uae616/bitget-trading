import time


def _utc_day(ts: float | None = None) -> str:
    t = ts if ts is not None else time.time()
    return time.strftime("%Y-%m-%d", time.gmtime(t))


def _equity_usdt(state: dict, prices: dict, coins: list[str]) -> float:
    cash = float(state.get("cash_usdt", 0.0))
    positions = state.get("positions", {}) or {}
    pos_value = 0.0
    for coin in coins:
        pos = positions.get(coin)
        if not pos:
            continue
        amt = float(pos.get("amount", 0.0))
        px = float(prices.get(coin, 0.0))
        pos_value += amt * px
    return cash + pos_value


def evaluate_risk_guardrail(cfg: dict, state: dict, snapshot: dict, log=None) -> dict:
    risk_cfg = cfg.get("risk", {}) or {}
    enabled = bool(risk_cfg.get("enabled", False))

    risk_state = state.setdefault("risk", {})
    risk_state.setdefault("halted", False)
    risk_state.setdefault("halt_reason", "")
    risk_state.setdefault("current_day", "")
    risk_state.setdefault("day_start_equity_usdt", 0.0)
    risk_state.setdefault("last_alert_day", "")

    if not enabled:
        return {"halted": bool(risk_state.get("halted", False)), "triggered": False}

    prices = (snapshot or {}).get("prices", {}) or {}
    coins = [c.upper() for c in cfg.get("portfolio", {}).get("coins", [])]
    if not prices or not coins:
        return {"halted": bool(risk_state.get("halted", False)), "triggered": False}

    today = _utc_day()
    equity = _equity_usdt(state, prices, coins)

    if not risk_state.get("current_day") or risk_state.get("current_day") != today:
        risk_state["current_day"] = today
        risk_state["day_start_equity_usdt"] = float(equity)
        risk_state["halted"] = False
        risk_state["halt_reason"] = ""
        risk_state["last_alert_day"] = ""
        if log:
            log.info(f"[RISK] New UTC day baseline: {today} equity={equity:.2f}")

    day_start = float(risk_state.get("day_start_equity_usdt", 0.0))
    if day_start <= 0:
        risk_state["day_start_equity_usdt"] = float(equity)
        day_start = float(equity)

    loss_pct = max(0.0, (day_start - equity) / day_start)
    limit_pct = float(risk_cfg.get("daily_loss_limit_pct", 0.05))

    if loss_pct >= limit_pct and not bool(risk_state.get("halted", False)):
        reason = (
            f"Daily loss limit reached: loss={loss_pct * 100:.2f}% "
            f"limit={limit_pct * 100:.2f}% "
            f"(start={day_start:.2f} equity={equity:.2f})"
        )
        risk_state["halted"] = True
        risk_state["halt_reason"] = reason
        if log:
            log.error(f"[RISK][HALT] {reason}")
        return {
            "halted": True,
            "triggered": True,
            "reason": reason,
            "day": today,
            "equity": equity,
            "day_start": day_start,
            "loss_pct": loss_pct,
            "limit_pct": limit_pct,
        }

    return {
        "halted": bool(risk_state.get("halted", False)),
        "triggered": False,
        "reason": str(risk_state.get("halt_reason", "") or ""),
        "day": today,
        "equity": equity,
        "day_start": day_start,
        "loss_pct": loss_pct,
        "limit_pct": limit_pct,
    }
