from ..utils.symbols import spot_symbol, pair_key
from ..utils.math_utils import floor_to_step, floor_to_precision
from .accounting import apply_sell_fill_wac, apply_buy_fill, parse_spot_market_order

def execute_actions(cfg: dict, state: dict, actions: list, log,
                    spot_api=None, convert_api=None,
                    spot_filters=None, convert_limits=None,
                    fee_to_usdt_fn=None, price_cache=None):
    dry_run = bool(cfg['bot'].get('dry_run', True))
    quote = cfg['portfolio']['quote_asset']

    results = []

    # simple cooldown tracking
    cooldown = int(cfg['portfolio']['max_trade_per_symbol_cooldown_sec'])
    last_trade_ts = state.setdefault('meta', {}).setdefault('last_trade_ts', {})

    import time as _time
    now = _time.time()

    for a in actions:
        coin = a['coin']
        # cooldown
        last = float(last_trade_ts.get(coin, 0.0))
        if now - last < cooldown:
            continue

        if a['type'] == 'TAKE_PROFIT_SELL':
            qty = float(a['qty'])
            if qty <= 0:
                continue

            sym = spot_symbol(coin, quote)
            f = (spot_filters or {}).get(sym, {'min_notional': 0.0, 'step_size': 0.0, 'min_qty': 0.0})
            min_notional = float(f.get('min_notional', 0.0))
            step_size = float(f.get('step_size', 0.0))
            min_qty = float(f.get('min_qty', 0.0))

            # step flooring (Spot)
            qty_spot = floor_to_step(qty, step_size) if step_size else qty
            notional = qty_spot * float(a.get('price', 0.0))

            # Convert fallback thresholds
            pk = pair_key(coin, quote)
            cl = (convert_limits or {}).get(pk, {'min_notional': 1.0, 'precision': 8})
            convert_min = float(cl.get('min_notional', 1.0))
            convert_prec = int(cl.get('precision', 8))

            if qty_spot < min_qty:
                continue

            if dry_run:
                log.info(f"[DRY_RUN] SELL {coin} qty={qty_spot:.8f} notional~{notional:.2f}")
                last_trade_ts[coin] = now
                results.append({'action': a, 'status': 'DRY_RUN'})
                continue

            # Route Spot vs Convert
            if notional >= min_notional and spot_api:
                order = spot_api.market_sell(coin, qty_spot, quote)
                exec_qty, exec_quote, fee_usdt = parse_spot_market_order(order, fee_to_usdt_fn=fee_to_usdt_fn)
                apply_sell_fill_wac(state, coin, exec_qty, exec_quote, fee_usdt, harvested=True)
                log.info(f"SPOT SELL {coin}: +{exec_quote:.2f} {quote} fee~{fee_usdt:.4f} realized updated")
                last_trade_ts[coin] = now
                results.append({'action': a, 'status': 'SPOT_OK'})
            elif notional >= convert_min and convert_api:
                qty_conv = floor_to_precision(qty, convert_prec)
                st = convert_api.convert_sell_to_usdt(coin, qty_conv)
                if not st or st.get('orderStatus') != 'SUCCESS':
                    log.warning(f"CONVERT SELL {coin} failed/timeout")
                    results.append({'action': a, 'status': 'CONVERT_FAIL'})
                else:
                    exec_qty = float(st['fromAmount'])
                    exec_quote = float(st['toAmount'])
                    apply_sell_fill_wac(state, coin, exec_qty, exec_quote, 0.0, harvested=True)
                    log.info(f"CONVERT SELL {coin}: +{exec_quote:.2f} {quote} (spread implicit)")
                    last_trade_ts[coin] = now
                    results.append({'action': a, 'status': 'CONVERT_OK'})
            else:
                results.append({'action': a, 'status': 'BELOW_MIN'})
            continue

        if a['type'] == 'DIP_BUY':
            quote_qty = float(a['quote_qty'])
            if quote_qty <= 0:
                continue


            if dry_run: 
                # simulate a fill at the current snapshot price 
                price = float(a.get("price", 0.0)) 
                if price > 0: 
                    qty = quote_qty / price # approximate 
                    # update accounting as if a buy happened         
                    apply_buy_fill(state, coin, qty, quote_qty, fee_usdt=0.0)     
                log.info(f"[DRY_RUN] BUY {coin} spend={quote_qty:.2f} {quote} (simulated fill)") 
                last_trade_ts[coin] = now 
                results.append({'action': a, 'status': 'DRY_RUN_SIM'}) 
                continue


            if spot_api:
                order = spot_api.market_buy_quote(coin, quote_qty, quote)
                # For buy: executedQty is base; cummulativeQuoteQty is quote spent
                exec_qty = float(order.get('executedQty', 0.0))
                exec_quote = float(order.get('cummulativeQuoteQty', 0.0) or quote_qty)
                # fee estimate from fills (optional)
                exec_qty2, exec_quote2, fee_usdt = parse_spot_market_order(order, fee_to_usdt_fn=fee_to_usdt_fn)
                apply_buy_fill(state, coin, exec_qty2, exec_quote2, fee_usdt)
                log.info(f"SPOT BUY {coin}: qty={exec_qty2:.8f} cost={exec_quote2:.2f} fee~{fee_usdt:.4f}")
                last_trade_ts[coin] = now
                results.append({'action': a, 'status': 'SPOT_OK'})
            continue

    return results

