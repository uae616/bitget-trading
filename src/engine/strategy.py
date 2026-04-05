from .take_profit import update_pending_profit_target, compute_qty_to_realize_profit_target
from .dip_buy import decide_dip_buy


def _log(log, msg: str):
    if log:
        try:
            log.info(msg)
        except Exception:
            pass


def _inc_metric(state: dict, key: str, delta: float = 1.0):
    metrics = state.setdefault("metrics", {})
    current = metrics.get(key, 0.0)
    try:
        current_val = float(current)
    except Exception:
        current_val = 0.0
    metrics[key] = current_val + float(delta)


def _get_cash(state: dict) -> float:
    return float(state.get("cash_usdt", 0.0))


def _positions(state: dict) -> dict:
    return state.get("positions", {}) or {}


def _owned_amount(positions: dict, coin: str) -> float:
    pos = positions.get(coin)
    return float(pos.get("amount", 0.0)) if pos else 0.0


def _avg_price(positions: dict, coin: str) -> float:
    pos = positions.get(coin)
    return float(pos.get("avg_price", 0.0)) if pos else 0.0


def _sig_get(sig, key: str, default=None):
    if sig is None:
        return default
    if isinstance(sig, dict):
        return sig.get(key, default)
    return getattr(sig, key, default)


def _ranked_coins(coins: list, momentum_z: dict) -> list:
    ranked = [(c, float(momentum_z.get(c, 0.0))) for c in coins]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _position_value_usdt(positions: dict, coin: str, prices: dict) -> float:
    amt = _owned_amount(positions, coin)
    px = float(prices.get(coin, 0.0))
    return amt * px


def _portfolio_equity_usdt(state: dict, prices: dict, coins: list) -> float:
    cash = _get_cash(state)
    pos = _positions(state)
    pos_value = sum(_position_value_usdt(pos, c, prices) for c in coins)
    return cash + pos_value


def _dynamic_min_position_usdt(cfg: dict, equity: float, n: int) -> float:
    entry = cfg.get("entry", {})
    build_fraction = float(entry.get("build_fraction", 0.35))
    floor_usdt = float(entry.get("min_pos_floor_usdt", 8.0))
    ceiling_usdt = float(entry.get("min_pos_ceiling_usdt", 30.0))

    if n <= 0:
        return floor_usdt

    target_weight = 1.0 / n
    dyn = equity * target_weight * build_fraction
    return _clamp(dyn, floor_usdt, ceiling_usdt)


def _median(values: list[float]) -> float:
    vals = sorted([v for v in values if v is not None])
    if not vals:
        return 0.0
    m = len(vals) // 2
    if len(vals) % 2 == 1:
        return float(vals[m])
    return float((vals[m - 1] + vals[m]) / 2.0)


def _vol_mult(cfg: dict, coin: str, volatility: dict) -> float:
    """
    Volatility multiplier affects ONLY the minimum threshold.
    mult = clamp(min_mult, (vol_coin / median_vol) ** k, max_mult)
    """
    entry = cfg.get("entry", {})
    enabled = bool(entry.get("vol_adjust_enabled", False))
    if not enabled:
        return 1.0

    vol_k = float(entry.get("vol_k", 0.5))
    min_mult = float(entry.get("vol_min_mult", 0.7))
    max_mult = float(entry.get("vol_max_mult", 1.4))

    vols = []
    for v in volatility.values():
        try:
            vols.append(float(v))
        except Exception:
            pass

    med = _median(vols)
    if med <= 0:
        return 1.0

    vcoin = float(volatility.get(coin, med))
    ratio = vcoin / med

    try:
        raw = ratio ** vol_k
    except Exception:
        raw = 1.0

    return _clamp(raw, min_mult, max_mult)


def _coin_needs_build(cfg: dict, coin: str, positions: dict, prices: dict, coin_min: float) -> tuple[bool, float, float, float]:
    """
    needs build if value < coin_min*(1 - buffer)
    built enough if value >= coin_min*(1 + buffer)
    Returns: (needs_build, value, low, high)
    """
    entry = cfg.get("entry", {})
    buf = float(entry.get("min_buffer_pct", 0.10))

    value = _position_value_usdt(positions, coin, prices)

    # no position -> needs build
    if value <= 0:
        low = coin_min * (1.0 - buf)
        high = coin_min * (1.0 + buf)
        return True, value, low, high

    low = coin_min * (1.0 - buf)
    high = coin_min * (1.0 + buf)

    if value < low:
        return True, value, low, high
    if value >= high:
        return False, value, low, high

    # in buffer zone: treat as built enough for now
    return False, value, low, high


def _compute_reserve(cfg: dict, cash: float) -> float:
    entry = cfg.get("entry", {})
    reserve_ratio = float(entry.get("reserve_ratio", 0.25))
    reserve_floor = float(entry.get("reserve_floor_usdt", 5.0))
    return max(reserve_floor, cash * reserve_ratio)


def _pick_best_dip_buy(cfg: dict, state: dict, prices: dict, momentum_z: dict, coins: list, log=None):
    """
    In CHOP mode: buy only dips among owned coins.
    Choose the deepest dip (avg/price - 1) that passes decide_dip_buy().
    """
    positions = _positions(state)
    best = None
    best_ratio = 0.0

    for coin in coins:
        if coin not in prices:
            continue
        if _owned_amount(positions, coin) <= 0:
            continue

        price = float(prices[coin])
        avg = _avg_price(positions, coin)
        if avg <= 0:
            continue

        if price >= avg:
            continue

        mz = float(momentum_z.get(coin, 0.0))
        spend = decide_dip_buy(cfg, state, coin, price, mz)
        if spend <= 0:
            continue

        dip_ratio = (avg / price) - 1.0
        if dip_ratio > best_ratio:
            best_ratio = dip_ratio
            best = {
                "type": "DIP_BUY",
                "coin": coin,
                "quote_qty": float(spend),
                "price": float(price),
                "momentum_z": float(mz),
                "reason": f"dip_buy_best (dip={dip_ratio:.2%})"
            }

    if best:
        _log(log, f"[DECISION][CHOP] selected={best['coin']} spend={best['quote_qty']:.2f} "
                  f"price={best['price']:.6f} mz={best['momentum_z']:.2f} reason={best.get('reason','')}")
    else:
        _log(log, "[NO_BUY][CHOP] No dip candidate matched (no price<avg or dip rules blocked).")

    return best


def decide_actions(cfg: dict, state: dict, log, snapshot: dict, return_context: bool = False):
    """
    Momentum rotation + hybrid regime with FULL decision trace.
    """
    actions = []
    alerts_cfg = cfg.get("alerts", {})
    near_signal_z_delta = float(alerts_cfg.get("near_signal_z_delta", 0.12))
    near_signal_gap_delta = float(alerts_cfg.get("near_signal_gap_delta", 0.08))
    near_signal_cash_ratio = float(alerts_cfg.get("near_signal_cash_ratio", 0.9))

    context = {
        "signal": None,
        "near_miss": None,
    }

    def _set_near_miss(msg: str):
        if not context.get("near_miss"):
            context["near_miss"] = msg

    def _return():
        if return_context:
            return actions, context
        return actions
    if not snapshot or "prices" not in snapshot:
        _log(log, "[NO_BUY] Snapshot missing prices.")
        _inc_metric(state, "strategy.no_buy.snapshot_missing_prices")
        context["near_miss"] = "snapshot_missing_prices"
        return _return()

    prices = snapshot.get("prices", {})
    momentum_z = snapshot.get("momentum_z", {})
    volatility = snapshot.get("volatility", {}) or {}
    risk_cfg = cfg.get("risk", {}) or {}
    spot_opp_close_enabled = bool(risk_cfg.get("spot_opposite_close_enabled", False))
    spot_opp_close_loss_pct = float(risk_cfg.get("spot_opposite_close_loss_pct", 0.03))
    spot_opp_close_first_loss_pct = float(risk_cfg.get("spot_opposite_close_first_loss_pct", spot_opp_close_loss_pct))
    spot_opp_close_first_close_ratio = float(risk_cfg.get("spot_opposite_close_first_close_ratio", 0.5))
    spot_opp_close_second_loss_pct = float(risk_cfg.get("spot_opposite_close_second_loss_pct", 0.10))
    spot_opp_close_second_close_ratio = float(risk_cfg.get("spot_opposite_close_second_close_ratio", 1.0))
    spot_opp_close_momentum_z_max = float(risk_cfg.get("spot_opposite_close_momentum_z_max", -0.10))
    scanner_signal_sell_enabled = bool(risk_cfg.get("spot_scanner_signal_sell_enabled", False))
    scanner_signal_sell_min_score = int(risk_cfg.get("spot_scanner_signal_sell_min_score", 5))
    scanner_signal_sell_close_ratio = float(risk_cfg.get("spot_scanner_signal_sell_close_ratio", 1.0))

    coins = [c.upper() for c in cfg["portfolio"]["coins"]]
    positions = _positions(state)
    cash = _get_cash(state)

    ranked = _ranked_coins(coins, momentum_z)
    force_sell_coins: set[str] = set()

    # Basic trace header each cycle (strategy side)
    _log(log, f"[TRACE] cash={cash:.2f} positions={list(positions.keys())} ranked={ranked}")

    # -----------------------------
    # STOP LOSS / Opposite-direction close (spot)
    # -----------------------------
    if spot_opp_close_enabled:
        stage_map = state.setdefault("meta", {}).setdefault("spot_stoploss_stage", {})
        for coin in coins:
            if coin not in prices:
                continue
            amt = _owned_amount(positions, coin)
            if amt <= 0:
                stage_map.pop(coin, None)
                continue
            avg = _avg_price(positions, coin)
            if avg <= 0:
                continue
            price = float(prices[coin])
            if price <= 0:
                continue

            pnl_pct = (price - avg) / avg
            mz = float(momentum_z.get(coin, 0.0))
            stage = int(stage_map.get(coin, 0) or 0)

            # Stage-2: deeper loss => close remaining (or configured ratio)
            if (
                stage < 2
                and pnl_pct <= -spot_opp_close_second_loss_pct
                and mz <= spot_opp_close_momentum_z_max
            ):
                qty_to_close = float(amt * max(0.0, min(1.0, spot_opp_close_second_close_ratio)))
                if qty_to_close > 0:
                    actions.append({
                        "type": "STOP_LOSS_SELL",
                        "coin": coin,
                        "qty": qty_to_close,
                        "price": float(price),
                        "reason": f"opposite_dir_loss_stage2 pnl={pnl_pct:.2%} mz={mz:.2f}",
                    })
                    stage_map[coin] = 2
                    force_sell_coins.add(coin)
                    _inc_metric(state, "strategy.action.stop_loss_sell")
                    _log(
                        log,
                        f"[DECISION][STOP2] coin={coin} qty={qty_to_close:.8f} price={price:.6f} "
                        f"pnl={pnl_pct:.2%} mz={mz:.2f}",
                    )
                continue

            # Stage-1: first loss trigger => partial close (default half)
            if (
                stage < 1
                and pnl_pct <= -spot_opp_close_first_loss_pct
                and mz <= spot_opp_close_momentum_z_max
            ):
                qty_to_close = float(amt * max(0.0, min(1.0, spot_opp_close_first_close_ratio)))
                if qty_to_close <= 0:
                    continue
                actions.append({
                    "type": "STOP_LOSS_SELL",
                    "coin": coin,
                    "qty": qty_to_close,
                    "price": float(price),
                    "reason": f"opposite_dir_loss_stage1 pnl={pnl_pct:.2%} mz={mz:.2f}",
                })
                stage_map[coin] = 1
                force_sell_coins.add(coin)
                _inc_metric(state, "strategy.action.stop_loss_sell")
                _log(
                    log,
                    f"[DECISION][STOP1] coin={coin} qty={qty_to_close:.8f} price={price:.6f} "
                    f"pnl={pnl_pct:.2%} mz={mz:.2f}",
                )

    # -----------------------------
    # Scanner-signal sell bridge (optional)
    # -----------------------------
    if scanner_signal_sell_enabled:
        scanner_signals = snapshot.get("signals", {}) or {}
        prev_sig_map = state.setdefault("meta", {}).setdefault("scanner_prev_direction", {})
        close_ratio = max(0.0, min(1.0, scanner_signal_sell_close_ratio))

        for coin in coins:
            if coin in force_sell_coins:
                continue
            amt = _owned_amount(positions, coin)
            if amt <= 0:
                prev_sig_map.pop(coin, None)
                continue
            sig = scanner_signals.get(coin)
            direction = str(_sig_get(sig, "direction", "HOLD")).upper()
            score = int(_sig_get(sig, "score", 0) or 0)
            prev_direction = str(prev_sig_map.get(coin, "HOLD")).upper()

            if (
                direction == "SELL"
                and score >= scanner_signal_sell_min_score
                and prev_direction != "SELL"
                and coin in prices
            ):
                qty_to_close = float(amt * close_ratio)
                if qty_to_close > 0:
                    price = float(prices[coin])
                    actions.append({
                        "type": "STOP_LOSS_SELL",
                        "coin": coin,
                        "qty": qty_to_close,
                        "price": price,
                        "reason": f"scanner_signal_sell score={score}",
                    })
                    force_sell_coins.add(coin)
                    _inc_metric(state, "strategy.action.scanner_signal_sell")
                    _log(
                        log,
                        f"[DECISION][SCANNER_SELL] coin={coin} qty={qty_to_close:.8f} "
                        f"price={price:.6f} score={score} prev={prev_direction}->SELL",
                    )

            prev_sig_map[coin] = direction

    # -----------------------------
    # TAKE PROFIT (sells)
    # -----------------------------
    if cfg["profit_take"]["enabled"]:
        for coin in coins:
            if coin in force_sell_coins:
                continue
            if coin not in prices:
                continue
            if _owned_amount(positions, coin) <= 0:
                state.setdefault('harvest', {}).setdefault('pending_profit_target', {})[coin] = 0.0
                continue

            price = float(prices[coin])
            pending = update_pending_profit_target(cfg, state, coin, price)
            qty_tp = compute_qty_to_realize_profit_target(cfg, state, coin, price)

            if qty_tp > 0:
                actions.append({
                    "type": "TAKE_PROFIT_SELL",
                    "coin": coin,
                    "qty": float(qty_tp),
                    "price": float(price),
                    "pending": float(pending),
                    "reason": "profit_target"
                })
                _log(log, f"[DECISION][SELL] coin={coin} qty={qty_tp:.8f} price={price:.6f} pending={pending:.2f}")
                _inc_metric(state, "strategy.action.take_profit_sell")

    # -----------------------------
    # BUY LOGIC (max one buy)
    # -----------------------------
    if not cfg["dip_buy"]["enabled"]:
        _log(log, "[NO_BUY] dip_buy disabled.")
        _inc_metric(state, "strategy.no_buy.dip_buy_disabled")
        context["near_miss"] = "dip_buy_disabled"
        return _return()

    min_buy_cfg = float(cfg["dip_buy"]["min_buy_usdt"])
    min_sell_notional = float(cfg.get("execution", {}).get("min_sell_notional_usdt", 0.0))
    dust_safety_ratio = float(cfg.get("dip_buy", {}).get("dust_safety_ratio", 1.2))
    min_buy_safe = min_sell_notional * max(1.0, dust_safety_ratio) if min_sell_notional > 0 else 0.0
    min_buy = max(min_buy_cfg, min_buy_safe)
    if min_buy > min_buy_cfg:
        _log(
            log,
            f"[TRACE][DUST_GUARD] min_buy adjusted {min_buy_cfg:.2f}->{min_buy:.2f} "
            f"(sell_min={min_sell_notional:.2f} ratio={max(1.0, dust_safety_ratio):.2f})",
        )
    if cash < min_buy:
        _log(log, f"[NO_BUY][CASH] cash={cash:.2f} < min_buy={min_buy:.2f}")
        _inc_metric(state, "strategy.no_buy.cash_below_min_buy")
        if cash >= (min_buy * near_signal_cash_ratio):
            _set_near_miss(f"near_cash_threshold cash={cash:.2f} min_buy={min_buy:.2f}")
        else:
            _set_near_miss(f"cash_below_min_buy cash={cash:.2f} min_buy={min_buy:.2f}")
        return _return()

    # Reserve buffer
    reserve = _compute_reserve(cfg, cash)
    spendable_cash = max(0.0, cash - reserve)
    if spendable_cash < min_buy:
        _log(log, f"[NO_BUY][BUFFER] cash={cash:.2f} reserve={reserve:.2f} spendable={spendable_cash:.2f} < min_buy={min_buy:.2f}")
        _inc_metric(state, "strategy.no_buy.reserve_buffer_block")
        if spendable_cash >= (min_buy * near_signal_cash_ratio):
            _set_near_miss(
                f"near_reserve_threshold cash={cash:.2f} reserve={reserve:.2f} "
                f"spendable={spendable_cash:.2f} min_buy={min_buy:.2f}"
            )
        else:
            _set_near_miss(
                f"reserve_buffer_block cash={cash:.2f} reserve={reserve:.2f} "
                f"spendable={spendable_cash:.2f} min_buy={min_buy:.2f}"
            )
        return _return()

    # Spend size (not affected by volatility)
    cap_ratio = float(cfg["dip_buy"]["max_buy_value_ratio_per_cycle"])
    spend_cap = spendable_cash * cap_ratio
    spend = max(min_buy, min(spend_cap, spendable_cash))

    # Momentum gating
    require_floor = bool(cfg["dip_buy"].get("require_momentum_not_too_negative", True))
    floor_z = float(cfg["dip_buy"].get("momentum_floor_z", -0.5))

    # Base dynamic minimum (equity)
    equity = _portfolio_equity_usdt(state, prices, coins)
    dyn_min = _dynamic_min_position_usdt(cfg, equity, len(coins))

    _log(log, f"[TRACE] equity={equity:.2f} base_min={dyn_min:.2f} reserve={reserve:.2f} spendable={spendable_cash:.2f} spend={spend:.2f}")

    # 1) Rotation build: buy strongest coin that needs building
    for coin, score in ranked:
        if coin not in prices:
            continue

        mult = _vol_mult(cfg, coin, volatility)
        coin_min = dyn_min * mult
        needs, value, low, high = _coin_needs_build(cfg, coin, positions, prices, coin_min)

        _log(log, f"[TRACE][CHECK] coin={coin} z={score:.2f} value={value:.2f} coin_min={coin_min:.2f} band=({low:.2f}..{high:.2f}) mult={mult:.2f} needs={needs}")

        if not needs:
            continue

        if require_floor and score < floor_z:
            _log(log, f"[NO_BUY][FLOOR][ROTATION] coin={coin} z={score:.2f} < floor_z={floor_z:.2f}")
            _inc_metric(state, "strategy.no_buy.rotation_floor_block")
            shortfall = floor_z - score
            if shortfall <= near_signal_z_delta:
                _set_near_miss(
                    f"near_rotation_floor coin={coin} z={score:.2f} floor_z={floor_z:.2f} shortfall={shortfall:.2f}"
                )
            else:
                _set_near_miss(f"rotation_floor_block coin={coin} z={score:.2f} floor_z={floor_z:.2f}")
            return _return()

        actions.append({
            "type": "DIP_BUY",
            "coin": coin,
            "quote_qty": float(spend),
            "price": float(prices[coin]),
            "momentum_z": float(score),
            "reason": f"rotation_build (base_min={dyn_min:.2f}, mult={mult:.2f}, coin_min={coin_min:.2f}, z={score:.2f})"
        })
        context["signal"] = f"BUY {coin} spend={spend:.2f} reason=rotation z={score:.2f}"
        _inc_metric(state, "strategy.signal.buy_rotation")

        _log(log, f"[DECISION][ROTATION] BUY coin={coin} z={score:.2f} spend={spend:.2f} price={float(prices[coin]):.6f} "
                  f"value={value:.2f} base_min={dyn_min:.2f} mult={mult:.2f} coin_min={coin_min:.2f} reserve={reserve:.2f} spendable={spendable_cash:.2f}")
        return _return()  # one buy per cycle

    # 2) All built enough -> Hybrid regime C vs D
    entry_trend = cfg.get("trend", {})
    trend_entry_z = float(entry_trend.get("entry_z", 0.75))
    dominance_gap = float(entry_trend.get("dominance_gap", 0.25))

    top_coin, top_z = ranked[0]
    second_z = ranked[1][1] if len(ranked) > 1 else -999.0
    gap = top_z - second_z
    trend_mode = (top_z >= trend_entry_z) and (gap >= dominance_gap)

    _log(log, f"[TRACE][REGIME] top={top_coin} top_z={top_z:.2f} second_z={second_z:.2f} gap={gap:.2f} "
              f"trend_entry_z={trend_entry_z:.2f} dominance_gap={dominance_gap:.2f} trend_mode={trend_mode}")

    if trend_mode:
        if require_floor and top_z < floor_z:
            _log(log, f"[NO_BUY][FLOOR][TREND] top={top_coin} top_z={top_z:.2f} < floor_z={floor_z:.2f}")
            _inc_metric(state, "strategy.no_buy.trend_floor_block")
            shortfall = floor_z - top_z
            if shortfall <= near_signal_z_delta:
                _set_near_miss(
                    f"near_trend_floor coin={top_coin} z={top_z:.2f} floor_z={floor_z:.2f} shortfall={shortfall:.2f}"
                )
            else:
                _set_near_miss(f"trend_floor_block coin={top_coin} z={top_z:.2f} floor_z={floor_z:.2f}")
            return _return()

        actions.append({
            "type": "DIP_BUY",
            "coin": top_coin,
            "quote_qty": float(spend),
            "price": float(prices[top_coin]),
            "momentum_z": float(top_z),
            "reason": f"trend_follow_top (z={top_z:.2f}, gap={gap:.2f})"
        })
        context["signal"] = f"BUY {top_coin} spend={spend:.2f} reason=trend z={top_z:.2f} gap={gap:.2f}"
        _inc_metric(state, "strategy.signal.buy_trend")

        _log(log, f"[DECISION][TREND] BUY coin={top_coin} top_z={top_z:.2f} gap={gap:.2f} spend={spend:.2f} "
                  f"price={float(prices[top_coin]):.6f} reserve={reserve:.2f} spendable={spendable_cash:.2f}")
        return _return()

    # Chop mode -> dip-buy only
    best_dip = _pick_best_dip_buy(cfg, state, prices, momentum_z, coins, log=log)
    if best_dip:
        actions.append(best_dip)
        context["signal"] = (
            f"BUY {best_dip['coin']} spend={float(best_dip.get('quote_qty', 0.0)):.2f} reason=dip "
            f"z={float(best_dip.get('momentum_z', 0.0)):.2f}"
        )
        _inc_metric(state, "strategy.signal.buy_dip")
        return _return()

    near_top = top_z >= (trend_entry_z - near_signal_z_delta)
    near_gap = gap >= (dominance_gap - near_signal_gap_delta)
    if near_top and near_gap:
        _set_near_miss(
            f"near_trend_entry coin={top_coin} top_z={top_z:.2f}/{trend_entry_z:.2f} gap={gap:.2f}/{dominance_gap:.2f}"
        )

    _log(log, "[NO_BUY] All coins built enough; no trend-follow; no dip candidate.")
    _inc_metric(state, "strategy.no_buy.all_built_no_trend_no_dip")
    _set_near_miss("no_buy_all_built_no_trend_no_dip")
    return _return()
