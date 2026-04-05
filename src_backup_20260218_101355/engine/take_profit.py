def update_pending_profit_target(cfg: dict, state: dict, coin: str, price: float) -> float:
    pos = state.get('positions', {}).get(coin)
    if not pos:
        return 0.0

    amount = float(pos.get('amount', 0.0))
    avg_price = float(pos.get('avg_price', 0.0))
    profit = (price - avg_price) * amount
    if profit <= 0:
        return 0.0

    ratio = cfg['profit_take']['profit_harvest_ratio']
    add_target = profit * ratio
    pending = state['harvest']['pending_profit_target'].get(coin, 0.0) + add_target
    state['harvest']['pending_profit_target'][coin] = pending
    return pending

def compute_qty_to_realize_profit_target(cfg: dict, state: dict, coin: str, price: float) -> float:
    pos = state.get('positions', {}).get(coin)
    if not pos:
        return 0.0

    amount = float(pos.get('amount', 0.0))
    avg_price = float(pos.get('avg_price', 0.0))
    pending = float(state['harvest']['pending_profit_target'].get(coin, 0.0))

    if pending < cfg['profit_take']['min_profit_target_usdt']:
        return 0.0

    profit_per_coin = price - avg_price
    if profit_per_coin <= 0:
        return 0.0

    qty_needed = pending / profit_per_coin

    # safety cap: don't sell > X% of position value per cycle
    cap_ratio = cfg['profit_take']['max_sell_value_ratio_per_cycle']
    max_qty = (amount * cap_ratio)
    qty_needed = min(qty_needed, max_qty)

    qty_needed = min(qty_needed, amount)
    return max(0.0, qty_needed)
