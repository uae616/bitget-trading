def decide_dip_buy(cfg: dict, state: dict, coin: str, price: float, momentum_z: float) -> float:
    if not cfg['dip_buy']['enabled']:
        return 0.0

    cash = float(state.get('cash_usdt', 0.0))
    min_buy = cfg['dip_buy']['min_buy_usdt']
    if cash < min_buy:
        return 0.0

    # optional momentum filter
    if cfg['dip_buy']['require_momentum_not_too_negative']:
        if momentum_z < cfg['dip_buy']['momentum_floor_z']:
            return 0.0

    # Buy only if price < avg_price (simple dip condition)
    pos = state.get('positions', {}).get(coin)
    if not pos:
        return 0.0
    avg_price = float(pos.get('avg_price', 0.0))
    if price >= avg_price:
        return 0.0

    # cap per cycle
    cap_ratio = cfg['dip_buy']['max_buy_value_ratio_per_cycle']
    max_spend = cash * cap_ratio
    spend = max(min_buy, min(max_spend, cash))
    return spend
