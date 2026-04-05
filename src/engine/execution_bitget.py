"""
Bitget execution adapter - maps CCXT Bitget to bot's execution interface.
"""

from core.errors import BotError


class BitgetAPIError(BotError):
    """Bitget API error wrapper."""
    def __init__(self, message: str):
        super().__init__(f"Bitget API error: {message}")


def _safe_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_ccxt_order(order: dict, symbol: str) -> dict:
    """Parse CCXT order response into our format."""
    fee = order.get('fee')
    fee_cost = fee.get('cost', 0.0) if isinstance(fee, dict) else 0.0
    filled_amount = _safe_float(order.get('filled', 0.0))
    filled_total = _safe_float(order.get('cost', 0.0))
    if filled_total <= 0.0:
        average = _safe_float(order.get('average', 0.0))
        filled_total = filled_amount * average if average > 0.0 else 0.0

    return {
        'orderId': order.get('id', ''),
        'symbol': symbol,
        'filledAmount': filled_amount,
        'filledTotal': filled_total,  # cost = filled * average
        'fees': _safe_float(fee_cost, 0.0),
        'feesCoin': fee.get('currency', '') if isinstance(fee, dict) else '',
        'status': order.get('status', 'unknown'),
    }


def execute_actions_bitget(
    cfg: dict,
    state: dict,
    actions: list,
    log,
    spot_api=None,
    spot_filters=None,
    fee_to_usdt_fn=None,
    price_cache=None
):
    """
    Bitget execution engine.
    
    Adapted from Binance execution to work with Bitget APIs.
    Key differences:
    - Symbol format: BTC-USDT (not BTCUSDT)
    - No ConvertAPI fallback (Bitget has Swap but not integrated)
    - Order response parsing via parse_bitget_order()
    - All market orders, no limit orders
    """
    from utils.symbols import pair_key
    from utils.math_utils import floor_to_step
    from engine.accounting import apply_sell_fill_wac, apply_buy_fill
    
    dry_run = bool(cfg.get("bot", {}).get("dry_run", True))
    quote = cfg.get("portfolio", {}).get("quote_asset", "USDT")
    min_sell_notional_usdt = float(cfg.get("execution", {}).get("min_sell_notional_usdt", 1.5))
    
    results = []
    
    def _inc_metric(key: str, delta: float = 1.0):
        metrics = state.setdefault("metrics", {})
        current = metrics.get(key, 0.0)
        try:
            current_val = float(current)
        except Exception:
            current_val = 0.0
        metrics[key] = current_val + float(delta)
    
    def _record(action: dict, status: str):
        results.append({"action": action, "status": status})
        _inc_metric(f"execution.status.{status}")

    def _inc_trade_count(side: str):
        _inc_metric(f"execution.trade.{side}.count", 1.0)
    
    # Cooldown tracking
    cooldown = int(cfg.get("portfolio", {}).get("max_trade_per_symbol_cooldown_sec", 300))
    last_trade_ts = state.setdefault("meta", {}).setdefault("last_trade_ts", {})
    
    import time as _time
    now = _time.time()
    
    # Ensure state structures exist
    state.setdefault("pnl", {}).setdefault("fees_usdt", 0.0)
    state.setdefault("harvest", {}).setdefault("pending_profit_target", {})
    state.setdefault("positions", {})
    
    for action in actions:
        coin = action.get("coin")
        if not coin:
            continue
        
        # Cooldown check
        last = float(last_trade_ts.get(coin, 0.0))
        if now - last < cooldown:
            remaining = int(cooldown - (now - last))
            log.info(f"[COOLDOWN] skip {coin} ({remaining}s remaining)")
            _inc_metric("execution.skip.cooldown")
            continue
        
        # CCXT symbol format: BTC/USDT
        ccxt_symbol = f"{coin}/{quote}"
        pk = pair_key(coin, quote)
        
        # Get filters for this symbol
        f = (spot_filters or {}).get(ccxt_symbol, {"min_notional": 0.0, "step_size": 0.0, "min_qty": 0.0})
        min_notional = float(f.get("min_notional", 0.0))
        min_sell_notional = max(min_notional, min_sell_notional_usdt)
        step_size = float(f.get("step_size", 0.1))
        min_qty = float(f.get("min_qty", 0.0))
        
        # ========== SELL (Take Profit) ==========
        if action["type"] in {"TAKE_PROFIT_SELL", "STOP_LOSS_SELL"}:
            qty = float(action.get("qty", 0.0))
            price = float(action.get("price", 0.0))
            harvested = action["type"] == "TAKE_PROFIT_SELL"
            
            if qty <= 0 or price <= 0:
                log.warning(f"[SELL] Invalid params for {coin}: qty={qty}, price={price}")
                _inc_metric("execution.skip.invalid_sell_action")
                continue
            
            # Round to step size
            qty_sell = floor_to_step(qty, step_size) if step_size else qty
            notional_value = qty_sell * price
            
            if notional_value < min_sell_notional:
                log.warning(
                    f"[SELL] {coin}: notional {notional_value} < min {min_sell_notional}. Skipping."
                )
                _inc_metric("execution.skip.notional_too_small")
                continue
            
            if dry_run:
                # Simulate the fill
                simulated_order = {
                    'id': f"sim_{coin}_{int(now*1000)}",
                    'symbol': ccxt_symbol,
                    'filled': qty_sell,
                    'cost': notional_value,
                    'fee': {'cost': notional_value * 0.002, 'currency': quote},
                    'status': 'closed'
                }
                parsed = parse_ccxt_order(simulated_order, ccxt_symbol)
                log.info(f"[SELL-SIM] {coin}: {qty_sell} @ {price} = {notional_value}")
                
                apply_sell_fill_wac(
                    state,
                    coin,
                    parsed["filledAmount"],
                    parsed["filledTotal"],
                    fee_usdt=parsed["fees"],
                    harvested=harvested,
                )
                last_trade_ts[coin] = now
                _inc_trade_count("sell")
                _record(action, "success")
                
            else:
                # Place real market sell order with CCXT
                try:
                    order = spot_api.exchange.create_market_sell_order(ccxt_symbol, qty_sell)
                    
                    parsed = parse_ccxt_order(order, ccxt_symbol)
                    log.info(f"[SELL] {coin}: {qty_sell} executed. OrderID: {parsed['orderId']}")
                    
                    apply_sell_fill_wac(
                        state,
                        coin,
                        parsed["filledAmount"],
                        parsed["filledTotal"],
                        fee_usdt=parsed["fees"],
                        harvested=harvested,
                    )
                    last_trade_ts[coin] = now
                    _inc_trade_count("sell")
                    _record(action, "success")
                    
                except Exception as e:
                    log.error(f"[SELL] {coin}: Exception: {e}")
                    _record(action, "error")
        
        # ========== BUY (Dip Buy) ==========
        elif action["type"] == "DIP_BUY":
            quote_qty = float(action.get("quote_qty", 0.0))
            
            if quote_qty <= 0:
                log.warning(f"[BUY] Invalid quote_qty for {coin}: {quote_qty}")
                _inc_metric("execution.skip.invalid_buy_action")
                continue
            
            if quote_qty < min_notional:
                log.warning(
                    f"[BUY] {coin}: quote_qty {quote_qty} < min_notional {min_notional}. Skipping."
                )
                _inc_metric("execution.skip.notional_too_small")
                continue
            
            if dry_run:
                # Simulate fill (estimate price from action or cache)
                price = float(action.get("price", 0.0))
                if price <= 0 and price_cache:
                    try:
                        price = price_cache.get_last_price(ccxt_symbol)
                    except Exception:
                        price = 0.0
                
                if price > 0:
                    qty_bought = quote_qty / price
                    qty_bought = floor_to_step(qty_bought, step_size) if step_size else qty_bought
                    
                    simulated_order = {
                        'id': f"sim_{coin}_{int(now*1000)}",
                        'symbol': ccxt_symbol,
                        'filled': qty_bought,
                        'cost': quote_qty,
                        'fee': {'cost': quote_qty * 0.002, 'currency': quote},
                        'status': 'closed'
                    }
                    parsed = parse_ccxt_order(simulated_order, ccxt_symbol)
                    log.info(f"[BUY-SIM] {coin}: {quote_qty} USDT @ {price} = {qty_bought} coins")
                    
                    apply_buy_fill(
                        state,
                        coin,
                        parsed["filledAmount"],
                        parsed["filledTotal"],
                        fee_usdt=parsed["fees"],
                    )
                    last_trade_ts[coin] = now
                    _inc_trade_count("buy")
                    _record(action, "success")
                else:
                    log.warning(f"[BUY] Could not estimate price for {coin}")
                    _record(action, "skipped")
            
            else:
                # Place real market buy order with CCXT
                try:
                    # With createMarketBuyOrderRequiresPrice=False, amount is quote cost to spend.
                    order = spot_api.exchange.create_market_buy_order(ccxt_symbol, quote_qty)
                    
                    parsed = parse_ccxt_order(order, ccxt_symbol)
                    log.info(f"[BUY] {coin}: Spent {quote_qty} USDT. OrderID: {parsed['orderId']}")
                    
                    apply_buy_fill(
                        state,
                        coin,
                        parsed["filledAmount"],
                        parsed["filledTotal"],
                        fee_usdt=parsed["fees"],
                    )
                    last_trade_ts[coin] = now
                    _inc_trade_count("buy")
                    _record(action, "success")
                    
                except Exception as e:
                    log.error(f"[BUY] {coin}: Exception: {e}")
                    _record(action, "error")
    
    return results
