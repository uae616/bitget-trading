def update_pending_profit_target(cfg: dict, state: dict, coin: str, price: float) -> float:
    harvest = state.setdefault('harvest', {}).setdefault('pending_profit_target', {})
    pos = state.get('positions', {}).get(coin)
    if not pos:
        harvest[coin] = 0.0
        return 0.0

    amount = float(pos.get('amount', 0.0))
    avg_price = float(pos.get('avg_price', 0.0))
    if amount <= 0 or avg_price <= 0:
        harvest[coin] = 0.0
        return 0.0

    profit = (price - avg_price) * amount
    if profit <= 0:
        harvest[coin] = 0.0
        return 0.0

    pt_cfg = cfg.get('profit_take', {})
    break_even_pct = float(pt_cfg.get('harvest_break_even_pct', 0.03))
    if avg_price <= 0 or price < (avg_price * (1.0 + break_even_pct)):
        harvest[coin] = 0.0
        return 0.0

    ratio = float(pt_cfg.get('profit_harvest_ratio', 0.2))
    pending = profit * ratio
    harvest[coin] = pending
    return pending

def compute_qty_to_realize_profit_target(cfg: dict, state: dict, coin: str, price: float) -> float:
    pos = state.get('positions', {}).get(coin)
    if not pos:
        return 0.0

    amount = float(pos.get('amount', 0.0))
    avg_price = float(pos.get('avg_price', 0.0))
    pending_targets = state.setdefault('harvest', {}).setdefault('pending_profit_target', {})
    if amount <= 0 or avg_price <= 0:
        pending_targets[coin] = 0.0
        return 0.0

    pending = float(pending_targets.get(coin, 0.0))
    pt_cfg = cfg.get('profit_take', {})
    exec_cfg = cfg.get('execution', {})

    min_profit_target = float(pt_cfg.get('min_profit_target_usdt', 1.0))
    min_sell_notional = float(exec_cfg.get('min_sell_notional_usdt', min_profit_target))
    min_harvest_notional = float(pt_cfg.get('min_harvest_notional_usdt', min_profit_target))
    trigger_min = max(min_profit_target, min_sell_notional, min_harvest_notional)

    if pending < trigger_min:
        return 0.0

    profit_per_coin = price - avg_price
    if profit_per_coin <= 0:
        return 0.0

    # Minimum gravity: only harvest when pending is a meaningful slice of position value.
    min_batch_pos_ratio = float(pt_cfg.get('harvest_min_batch_pos_ratio', 0.10))
    position_value = amount * price
    if position_value <= 0 or (pending / position_value) < min_batch_pos_ratio:
        return 0.0

    qty_needed = pending / profit_per_coin

    # safety cap: don't sell > X% of position value per cycle
    cap_ratio = float(pt_cfg.get('max_sell_value_ratio_per_cycle', 0.05))
    max_qty = (amount * cap_ratio)
    qty_needed = min(qty_needed, max_qty)

    qty_needed = min(qty_needed, amount)
    projected_profit = qty_needed * profit_per_coin
    if projected_profit < min_profit_target:
        return 0.0

    return max(0.0, qty_needed)
