from .take_profit import update_pending_profit_target, compute_qty_to_realize_profit_target
from .dip_buy import decide_dip_buy


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
    Option 3: volatility-adjusted multiplier, applied ONLY to the minimum threshold.
    mult = clamp(vol_min_mult, (vol_coin / median_vol) ** vol_k, vol_max_mult)
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

    # safe power transform
    try:
        raw = ratio ** vol_k
    except Exception:
        raw = 1.0

    return _clamp(raw, min_mult, max_mult)


def _coin_needs_build(cfg: dict, coin: str, positions: dict, prices: dict, coin_min: float) -> bool:
    """
    needs build if value < coin_min*(1 - buffer)
    built enough if value >= coin_min*(1 + buffer)
    """
    entry = cfg.get("entry", {})
    buf = float(entry.get("min_buffer_pct", 0.10))

    v = _position_value_usdt(positions, coin, prices)

    # no position -> needs build
    if v <= 0:
        return True

    low = coin_min * (1.0 - buf)
    high = coin_min * (1.0 + buf)

    if v < low:
        return True
    if v >= high:
        return False

    # in the buffer zone: treat as "built enough for now"
    return False


def _compute_reserve(cfg: dict, cash: float) -> float:
    entry = cfg.get("entry", {})
    reserve_ratio = float(entry.get("reserve_ratio", 0.25))
    reserve_floor = float(entry.get("reserve_floor_usdt", 5.0))
    return max(reserve_floor, cash * reserve_ratio)


def _pick_best_dip_buy(cfg: dict, state: dict, prices: dict, momentum_z: dict, coins: list):
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

    return best


def decide_actions(cfg: dict, state: dict, log, snapshot: dict) -> list:
    """
    Momentum rotation + hybrid regime, with:
    - reserve buffer (do not spend all cash)
    - dynamic minimum position sizing (equity-based)
    - volatility-adjusted minimum per coin (OPTIONAL)
    - hysteresis buffer band
    """
    actions = []
    if not snapshot or "prices" not in snapshot:
        return actions

    prices = snapshot.get("prices", {})
    momentum_z = snapshot.get("momentum_z", {})
    volatility = snapshot.get("volatility", {}) or {}

    coins = [c.upper() for c in cfg["portfolio"]["coins"]]
    positions = _positions(state)
    cash = _get_cash(state)

    # -----------------------------
    # TAKE PROFIT (sells)
    # -----------------------------
    if cfg["profit_take"]["enabled"]:
        for coin in coins:
            if coin not in prices:
                continue
            if _owned_amount(positions, coin) <= 0:
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

    # -----------------------------
    # BUY LOGIC (max one buy)
    # -----------------------------
    if not cfg["dip_buy"]["enabled"]:
        return actions

    min_buy = float(cfg["dip_buy"]["min_buy_usdt"])
    if cash < min_buy:
        return actions

    # Reserve buffer
    reserve = _compute_reserve(cfg, cash)
    spendable_cash = max(0.0, cash - reserve)
    if spendable_cash < min_buy:
        log.info(f"[BUFFER] cash={cash:.2f} reserve={reserve:.2f} spendable={spendable_cash:.2f} < min_buy")
        return actions

    # Spend size (unchanged by volatility — as you requested)
    cap_ratio = float(cfg["dip_buy"]["max_buy_value_ratio_per_cycle"])
    spend_cap = spendable_cash * cap_ratio
    spend = max(min_buy, min(spend_cap, spendable_cash))

    # Momentum gating (optional)
    require_floor = bool(cfg["dip_buy"].get("require_momentum_not_too_negative", True))
    floor_z = float(cfg["dip_buy"].get("momentum_floor_z", -0.5))

    # Base dynamic minimum (equity-based)
    equity = _portfolio_equity_usdt(state, prices, coins)
    dyn_min = _dynamic_min_position_usdt(cfg, equity, len(coins))

    ranked = _ranked_coins(coins, momentum_z)

    # 1) Rotation build: buy the strongest coin that needs building
    for coin, score in ranked:
        if coin not in prices:
            continue

        mult = _vol_mult(cfg, coin, volatility)
        coin_min = dyn_min * mult

        needs = _coin_needs_build(cfg, coin, positions, prices, coin_min)
        if not needs:
            continue

        if require_floor and score < floor_z:
            log.info(f"[ROTATION] Blocked: {coin} momentum_z={score:.2f} < floor {floor_z}")
            return actions

        actions.append({
            "type": "DIP_BUY",
            "coin": coin,
            "quote_qty": float(spend),
            "price": float(prices[coin]),
            "momentum_z": float(score),
            "reason": f"rotation_build (base_min={dyn_min:.2f}, mult={mult:.2f}, coin_min={coin_min:.2f}, z={score:.2f})"
        })
        return actions  # one buy per cycle

    # 2) All built enough -> Hybrid regime C vs D
    entry_trend = cfg.get("trend", {})
    trend_entry_z = float(entry_trend.get("entry_z", 0.75))
    dominance_gap = float(entry_trend.get("dominance_gap", 0.25))

    top_coin, top_z = ranked[0]
    second_z = ranked[1][1] if len(ranked) > 1 else -999.0
    trend_mode = (top_z >= trend_entry_z) and ((top_z - second_z) >= dominance_gap)

    if trend_mode:
        if require_floor and top_z < floor_z:
            log.info(f"[TREND] Blocked by floor: top_z={top_z:.2f} < floor {floor_z}")
            return actions

        actions.append({
            "type": "DIP_BUY",
            "coin": top_coin,
            "quote_qty": float(spend),
            "price": float(prices[top_coin]),
            "momentum_z": float(top_z),
            "reason": f"trend_follow_top (z={top_z:.2f}, gap={(top_z-second_z):.2f})"
        })
        return actions

    # Chop mode -> dip-buy only
    best_dip = _pick_best_dip_buy(cfg, state, prices, momentum_z, coins)
    if best_dip:
        actions.append(best_dip)

    return actions
