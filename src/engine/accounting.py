from utils.math_utils import floor_to_step, floor_to_precision

def apply_buy_fill(state: dict, coin: str, executed_qty: float, executed_quote_usdt: float, fee_usdt: float = 0.0, tag: str = 'BUY'):
    pos = state.setdefault('positions', {}).setdefault(coin, {'amount': 0.0, 'avg_price': 0.0})
    old_amt = float(pos.get('amount', 0.0))
    old_avg = float(pos.get('avg_price', 0.0))

    net_cost = executed_quote_usdt + fee_usdt
    new_amt = old_amt + executed_qty
    if new_amt <= 0:
        return

    new_avg = ((old_amt * old_avg) + net_cost) / new_amt
    pos['amount'] = new_amt
    pos['avg_price'] = new_avg

    state['cash_usdt'] = float(state.get('cash_usdt', 0.0)) - net_cost
    state['pnl']['fees_usdt'] = float(state['pnl'].get('fees_usdt', 0.0)) + fee_usdt

def apply_sell_fill_wac(state: dict, coin: str, executed_qty: float, executed_quote_usdt: float, fee_usdt: float = 0.0, tag: str = 'SELL', harvested: bool = False):
    pos = state.setdefault('positions', {}).setdefault(coin, {'amount': 0.0, 'avg_price': 0.0})
    avg_price = float(pos.get('avg_price', 0.0))

    cost_removed = executed_qty * avg_price
    net_proceeds = executed_quote_usdt - fee_usdt
    realized = net_proceeds - cost_removed

    pos['amount'] = float(pos.get('amount', 0.0)) - executed_qty
    if pos['amount'] <= 0:
        pos['amount'] = 0.0
        pos['avg_price'] = 0.0
        state.setdefault('harvest', {}).setdefault('pending_profit_target', {})[coin] = 0.0
    state['cash_usdt'] = float(state.get('cash_usdt', 0.0)) + net_proceeds

    state['pnl']['realized_profit_usdt'] = float(state['pnl'].get('realized_profit_usdt', 0.0)) + realized
    state['pnl']['fees_usdt'] = float(state['pnl'].get('fees_usdt', 0.0)) + fee_usdt

    if harvested:
        state['pnl']['harvested_profit_usdt'] = float(state['pnl'].get('harvested_profit_usdt', 0.0)) + max(0.0, realized)
        pending = state['harvest']['pending_profit_target'].get(coin, 0.0)
        state['harvest']['pending_profit_target'][coin] = max(0.0, pending - max(0.0, realized))

def parse_spot_market_order(order: dict, fee_to_usdt_fn=None, fallback_base_asset=None, last_price_fn=None) -> tuple[float,float,float]:
    executed_qty = float(order.get('executedQty', 0.0))
    executed_quote = float(order.get('cummulativeQuoteQty', 0.0) or 0.0)

    fee_usdt = 0.0
    fills = order.get('fills') or []

    if executed_quote == 0.0 and fills:
        executed_quote = sum(float(f['price']) * float(f['qty']) for f in fills)

    for f in fills:
        commission = float(f.get('commission', 0.0))
        asset = (f.get('commissionAsset') or '').upper()
        if commission <= 0 or not asset:
            continue

        if fee_to_usdt_fn:
            val = fee_to_usdt_fn(asset, commission)
            if val is not None:
                fee_usdt += val
                continue

        # very rough fallback if fee asset == base asset and we have last price
        if last_price_fn and fallback_base_asset and asset == fallback_base_asset.upper():
            try:
                fee_usdt += commission * float(last_price_fn())
            except Exception:
                pass

    return executed_qty, executed_quote, fee_usdt
