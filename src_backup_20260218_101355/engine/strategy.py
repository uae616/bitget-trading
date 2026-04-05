from ..utils.symbols import spot_symbol
from .momentum import momentum_scores
from .take_profit import update_pending_profit_target, compute_qty_to_realize_profit_target
from .dip_buy import decide_dip_buy

def decide_actions(cfg: dict, state: dict, log, price_cache=None) -> list:
    coins = cfg['portfolio']['coins']
    quote = cfg['portfolio']['quote_asset']

    # prices
    prices = {}
    if price_cache:
        for c in coins:
            sym = spot_symbol(c, quote)
            prices[c] = price_cache.get_last_price(sym)
    else:
        # if no cache provided, do nothing
        return []

    # momentum (placeholder)
    mom = momentum_scores(prices)

    actions = []
    for c in coins:
        price = prices[c]

        # update pending profit target
        if cfg['profit_take']['enabled']:
            pending = update_pending_profit_target(cfg, state, c, price)
            qty_tp = compute_qty_to_realize_profit_target(cfg, state, c, price)
            if qty_tp > 0:
                actions.append({'type': 'TAKE_PROFIT_SELL', 'coin': c, 'qty': qty_tp, 'price': price, 'pending': pending})

        # dip buy
        spend = decide_dip_buy(cfg, state, c, price, mom.get(c, 0.0))
        if spend > 0:
            actions.append({'type': 'DIP_BUY', 'coin': c, 'quote_qty': spend, 'price': price})

    return actions
