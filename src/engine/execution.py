from ..utils.symbols import spot_symbol, pair_key
from ..utils.math_utils import floor_to_step, floor_to_precision
from ..core.errors import BinanceAPIError
from .accounting import apply_sell_fill_wac, apply_buy_fill, parse_spot_market_order


def execute_actions(cfg: dict, state: dict, actions: list, log,
                    spot_api=None, convert_api=None,
                    spot_filters=None, convert_limits=None,
                    fee_to_usdt_fn=None, price_cache=None):
    """
    Execution engine:
    - In DRY_RUN: simulate fills ("paper trading") so state evolves
    - In LIVE: place real orders via Spot/Convert and apply accounting
    """
    dry_run = bool(cfg["bot"].get("dry_run", True))
    quote = cfg["portfolio"]["quote_asset"]
    enable_convert_buy_fallback = bool(cfg.get("execution", {}).get("enable_convert_buy_fallback", True))
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

    def _inc_trade_count(side: str):
        _inc_metric(f"execution.trade.{side}.count", 1.0)

    def _record(action: dict, status: str):
        results.append({"action": action, "status": status})
        _inc_metric(f"execution.status.{status}")

    def _add_activity(action: str, coin: str, message: str):
        acts = state.setdefault("activities", [])
        acts.append({"ts": _time.time(), "market": "spot", "action": action, "symbol": coin, "message": message})
        if len(acts) > 200:
            state["activities"] = acts[-200:]

    # cooldown tracking
    cooldown = int(cfg["portfolio"]["max_trade_per_symbol_cooldown_sec"])
    last_trade_ts = state.setdefault("meta", {}).setdefault("last_trade_ts", {})

    import time as _time
    now = _time.time()

    # ensure required top-level keys exist
    state.setdefault("pnl", {}).setdefault("fees_usdt", 0.0)
    state.setdefault("harvest", {}).setdefault("pending_profit_target", {})
    state.setdefault("positions", {})

    for a in actions:
        coin = a.get("coin")
        if not coin:
            continue

        # cooldown check
        last = float(last_trade_ts.get(coin, 0.0))
        if now - last < cooldown:
            log.info(f"[COOLDOWN] skip {coin} ({int(cooldown - (now-last))}s remaining)")
            _inc_metric("execution.skip.cooldown")
            continue

        # -----------------------------
        # SELL (Take Profit)
        # -----------------------------
        if a["type"] in {"TAKE_PROFIT_SELL", "STOP_LOSS_SELL"}:
            qty = float(a.get("qty", 0.0))
            price = float(a.get("price", 0.0))
            harvested = a["type"] == "TAKE_PROFIT_SELL"

            if qty <= 0 or price <= 0:
                _inc_metric("execution.skip.invalid_sell_action")
                continue

            sym = spot_symbol(coin, quote)

            f = (spot_filters or {}).get(sym, {"min_notional": 0.0, "step_size": 0.0, "min_qty": 0.0})
            min_notional = float(f.get("min_notional", 0.0))
            min_sell_notional = max(min_notional, min_sell_notional_usdt)
            step_size = float(f.get("step_size", 0.0))
            min_qty = float(f.get("min_qty", 0.0))

            qty_spot = floor_to_step(qty, step_size) if step_size else qty
            notional = qty_spot * price
            prev_amt = float(state.get("positions", {}).get(coin, {}).get("amount", 0.0))

            pk = pair_key(coin, quote)
            cl = (convert_limits or {}).get(pk, {"min_notional": 1.0, "precision": 8})
            convert_min = float(cl.get("min_notional", 1.0))
            convert_prec = int(cl.get("precision", 8))

            if qty_spot < min_qty:
                log.info(f"[SELL] skip {coin}: qty {qty_spot} < min_qty {min_qty}")
                _inc_metric("execution.skip.sell_below_min_qty")
                continue

            if dry_run:
                # ---- PAPER SELL ----
                executed_qty = qty_spot
                executed_quote = executed_qty * price
                fee_usdt = 0.0

                apply_sell_fill_wac(state, coin, executed_qty, executed_quote, fee_usdt, harvested=harvested)

                log.info(f"[DRY_RUN_SIM] SELL {coin} qty={executed_qty:.8f} "
                         f"quote~{executed_quote:.2f} {quote} price={price:.6f} (paper fill)")
                last_trade_ts[coin] = now
                _inc_trade_count("sell")
                _record(a, "DRY_RUN_SELL_SIM")
                continue

            # ---- LIVE SELL ----
            if notional >= min_sell_notional and spot_api:
                order = spot_api.market_sell(coin, qty_spot, quote)
                exec_qty, exec_quote, fee_usdt = parse_spot_market_order(order, fee_to_usdt_fn=fee_to_usdt_fn)
                apply_sell_fill_wac(state, coin, exec_qty, exec_quote, fee_usdt, harvested=harvested)
                post_amt = float(state.get("positions", {}).get(coin, {}).get("amount", 0.0))
                if prev_amt > 0 and post_amt <= 1e-12:
                    meta = state.setdefault("meta", {})
                    meta["spot_full_close_count"] = int(float(meta.get("spot_full_close_count", 0.0) or 0.0)) + 1
                log.info(f"SPOT SELL {coin}: +{exec_quote:.2f} {quote} fee~{fee_usdt:.4f}")
                _add_activity("SPOT_SELL", coin, f"quote={exec_quote:.4f} fee={fee_usdt:.6f}")
                last_trade_ts[coin] = now
                _inc_trade_count("sell")
                _record(a, "SPOT_OK")
            elif notional >= max(convert_min, min_sell_notional_usdt) and convert_api:
                qty_conv = floor_to_precision(qty, convert_prec)
                st = convert_api.convert_sell_to_usdt(coin, qty_conv)
                if not st or st.get("orderStatus") != "SUCCESS":
                    log.warning(f"CONVERT SELL {coin} failed/timeout")
                    _record(a, "CONVERT_FAIL")
                else:
                    exec_qty = float(st["fromAmount"])
                    exec_quote = float(st["toAmount"])
                    apply_sell_fill_wac(state, coin, exec_qty, exec_quote, 0.0, harvested=harvested)
                    post_amt = float(state.get("positions", {}).get(coin, {}).get("amount", 0.0))
                    if prev_amt > 0 and post_amt <= 1e-12:
                        meta = state.setdefault("meta", {})
                        meta["spot_full_close_count"] = int(float(meta.get("spot_full_close_count", 0.0) or 0.0)) + 1
                    log.info(f"CONVERT SELL {coin}: +{exec_quote:.2f} {quote} (spread implicit)")
                    _add_activity("SPOT_SELL_CONVERT", coin, f"quote={exec_quote:.4f}")
                    last_trade_ts[coin] = now
                    _inc_trade_count("sell")
                    _record(a, "CONVERT_OK")
            else:
                log.warning(f"[SELL] {coin}: notional {notional} < min {min_sell_notional}. Skipping.")
                _add_activity("SPOT_SELL_SKIPPED", coin, f"notional={notional:.6f} min={min_sell_notional:.2f}")
                _record(a, "SELL_BELOW_MIN")
            continue

        # -----------------------------
        # BUY (Dip / Rotation / Trend)
        # -----------------------------
        if a["type"] == "DIP_BUY":
            quote_qty = float(a.get("quote_qty", 0.0))
            price = float(a.get("price", 0.0))

            if quote_qty <= 0:
                _inc_metric("execution.skip.invalid_buy_action")
                continue

            if dry_run:
                # ---- PAPER BUY ----
                if price <= 0:
                    log.info(f"[DRY_RUN_SIM] BUY {coin} spend={quote_qty:.2f} {quote} (no price in action)")
                    last_trade_ts[coin] = now
                    _record(a, "DRY_RUN_BUY_NO_PRICE")
                    continue

                qty = quote_qty / price

                # Apply WAC buy accounting (fee = 0 for paper trade)
                apply_buy_fill(state, coin, qty, quote_qty, fee_usdt=0.0)

                log.info(f"[DRY_RUN_SIM] BUY {coin} spend={quote_qty:.2f} {quote} "
                         f"qty~{qty:.8f} price={price:.6f} (paper fill)")
                last_trade_ts[coin] = now
                _inc_trade_count("buy")
                _record(a, "DRY_RUN_BUY_SIM")
                continue

            # ---- LIVE BUY ----
            if spot_api:
                sym = spot_symbol(coin, quote)
                f = (spot_filters or {}).get(sym, {"min_notional": 0.0, "step_size": 0.0, "min_qty": 0.0})
                min_notional = float(f.get("min_notional", 0.0))
                step_size = float(f.get("step_size", 0.0))
                min_qty = float(f.get("min_qty", 0.0))

                quote_precision = 2 if str(quote).upper() == "USDT" else 8
                quote_qty_live = floor_to_precision(quote_qty, quote_precision)
                if quote_qty_live <= 0:
                    _record(a, "BUY_BELOW_PRECISION")
                    continue

                if min_notional > 0 and quote_qty_live < min_notional:
                    log.info(
                        f"[BUY] skip {coin}: quote_qty {quote_qty_live:.2f} < min_notional {min_notional:.2f}"
                    )
                    _record(a, "BUY_BELOW_MIN_NOTIONAL")
                    continue

                quote_qty_param = f"{quote_qty_live:.{quote_precision}f}"

                try:
                    try:
                        order = spot_api.market_buy_quote(coin, quote_qty_param, quote)
                    except BinanceAPIError as e:
                        payload = str(e.payload or "")
                        is_quote_precision_err = (
                            "quoteOrderQty" in payload and "too much precision" in payload
                        )
                        if not is_quote_precision_err or price <= 0:
                            raise

                        qty_from_quote = quote_qty_live / price
                        qty_spot = floor_to_step(qty_from_quote, step_size) if step_size else qty_from_quote

                        if qty_spot <= 0 or (min_qty > 0 and qty_spot < min_qty):
                            log.warning(
                                f"SPOT BUY {coin} precision retry skipped: qty {qty_spot:.8f} < min_qty {min_qty}"
                            )
                            _record(a, "BUY_PRECISION_RETRY_BELOW_MIN")
                            continue

                        log.warning(
                            f"SPOT BUY {coin} quoteOrderQty precision rejected; retrying with quantity={qty_spot:.8f}"
                        )
                        order = spot_api.market_buy_qty(coin, qty_spot, quote)

                    # parse fills for fee estimate if available
                    exec_qty, exec_quote, fee_usdt = parse_spot_market_order(order, fee_to_usdt_fn=fee_to_usdt_fn)

                    # Some exchanges return buy order executedQuote as cummulativeQuoteQty;
                    # parse_spot_market_order uses that or fills-based sum.
                    apply_buy_fill(state, coin, exec_qty, exec_quote, fee_usdt)

                    log.info(f"SPOT BUY {coin}: qty={exec_qty:.8f} cost={exec_quote:.2f} fee~{fee_usdt:.4f}")
                    _add_activity("SPOT_BUY", coin, f"quote={exec_quote:.4f} qty={exec_qty:.8f} fee={fee_usdt:.6f}")
                    last_trade_ts[coin] = now
                    _inc_trade_count("buy")
                    _record(a, "SPOT_OK")
                except Exception as e:
                    log.warning(f"SPOT BUY {coin} failed, trying CONVERT fallback: {e}")
                    if enable_convert_buy_fallback and convert_api:
                        try:
                            st = convert_api.convert_buy_from_usdt(coin, quote_qty_live)
                        except Exception as convert_err:
                            log.warning(f"CONVERT BUY {coin} request failed: {convert_err}")
                            _record(a, "BUY_FALLBACK_FAIL")
                            continue

                        if not st or st.get("orderStatus") != "SUCCESS":
                            log.warning(f"CONVERT BUY {coin} failed/timeout")
                            _record(a, "BUY_FALLBACK_FAIL")
                        else:
                            exec_quote = float(st.get("fromAmount", quote_qty_live))
                            exec_qty = float(st.get("toAmount", 0.0))
                            apply_buy_fill(state, coin, exec_qty, exec_quote, fee_usdt=0.0)
                            log.info(f"CONVERT BUY {coin}: qty={exec_qty:.8f} cost={exec_quote:.2f} {quote} (spread implicit)")
                            _add_activity("SPOT_BUY_CONVERT", coin, f"quote={exec_quote:.4f} qty={exec_qty:.8f}")
                            last_trade_ts[coin] = now
                            _inc_trade_count("buy")
                            _record(a, "CONVERT_BUY_OK")
                    elif not enable_convert_buy_fallback:
                        _record(a, "SPOT_FAIL_FALLBACK_DISABLED")
                    else:
                        _record(a, "SPOT_FAIL_NO_FALLBACK")
            else:
                _record(a, "NO_SPOT_API")
            continue

        # ignore unknown actions
        _record(a, "UNKNOWN_ACTION")

    return results
