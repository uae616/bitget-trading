from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import ccxt
import pandas as pd

from ..core.logger import setup_logger
from ..core.notify import send_telegram_message
from ..core.settings import load_config
from ..core.single_instance import AlreadyRunningError, acquire_single_instance_lock
from .indicators import rsi, sma
from .state import load_futures_state, save_futures_state


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _spot_symbol_from_perp(perp_symbol: str) -> str:
    if ":" in perp_symbol:
        return perp_symbol.split(":")[0]
    return perp_symbol


def _position_size(position: dict) -> float:
    contracts = position.get("contracts")
    if isinstance(contracts, (int, float)):
        return float(contracts)

    info = position.get("info") or {}
    for key in ("positionAmt", "size", "positionSize"):
        val = info.get(key)
        try:
            if val is not None:
                return abs(float(val))
        except Exception:
            pass
    return 0.0


def _position_side(position: dict) -> str:
    side = str(position.get("side") or "").lower()
    if side in {"long", "short"}:
        return side

    info = position.get("info") or {}
    val = info.get("positionAmt")
    try:
        if val is None:
            return ""
        amt = float(val)
        if amt > 0:
            return "long"
        if amt < 0:
            return "short"
    except Exception:
        pass
    return ""


def _position_notional(position: dict) -> float:
    notional = position.get("notional")
    if isinstance(notional, (int, float)):
        return abs(float(notional))

    info = position.get("info") or {}
    for key in ("notional", "positionValue"):
        val = info.get(key)
        try:
            if val is not None:
                return abs(float(val))
        except Exception:
            pass
    return 0.0


def _position_entry(position: dict) -> float:
    ep = position.get("entryPrice")
    if isinstance(ep, (int, float)):
        return float(ep)

    info = position.get("info") or {}
    for key in ("entryPrice", "avgPrice"):
        val = info.get(key)
        try:
            if val is not None:
                return float(val)
        except Exception:
            pass
    return 0.0


def _build_exchange(
    api_key: str,
    api_secret: str,
    api_passphrase: str,
    base_url: str,
    default_type: str = "swap",
):
    exchange = ccxt.bitget(
        {
            "apiKey": api_key,
            "secret": api_secret,
            "password": api_passphrase,
            "enableRateLimit": True,
            "options": {"defaultType": default_type},
        }
    )
    # Keep CCXT default Bitget endpoints unless explicitly customized elsewhere.
    # `base_url` is currently not overridden here because Bitget URL maps differ
    # from Binance-style public/private endpoint shapes.
    return exchange


def _fetch_balance_usdt(futures_exchange: ccxt.Exchange) -> tuple[float, float]:
    balance = futures_exchange.fetch_balance({"type": "swap"})
    usdt = balance.get("USDT", {}) if isinstance(balance, dict) else {}

    total = usdt.get("total") if isinstance(usdt, dict) else None
    free = usdt.get("free") if isinstance(usdt, dict) else None

    if total is None:
        total = balance.get("total", {}).get("USDT", 0.0)
    if free is None:
        free = balance.get("free", {}).get("USDT", 0.0)

    return float(total or 0.0), float(free or 0.0)


def _fetch_positions_map(futures_exchange: ccxt.Exchange, symbols: list[str] | None = None) -> dict[str, dict]:
    pos_map: dict[str, dict] = {}
    try:
        if symbols:
            positions = futures_exchange.fetch_positions(symbols)
            if not positions:
                positions = futures_exchange.fetch_positions(None, {"productType": "USDT-FUTURES"})
        else:
            positions = futures_exchange.fetch_positions(None, {"productType": "USDT-FUTURES"})
    except Exception:
        positions = []

    for p in positions or []:
        sym = str(p.get("symbol") or "")
        if not sym:
            continue
        qty = _position_size(p)
        if qty <= 0:
            continue
        pos_map[sym] = p
    return pos_map


def _compute_signal(df: pd.DataFrame, cfg: dict[str, Any]) -> dict[str, Any]:
    close = df["close"]
    rsi_len = int(cfg.get("rsi_len", 14))
    ma_len = int(cfg.get("ma_len", 50))
    rsi_long_max = float(cfg.get("rsi_long_max", 40.0))
    rsi_short_min = float(cfg.get("rsi_short_min", 60.0))

    latest_close = float(close.iloc[-1])
    latest_rsi = rsi(close, rsi_len)
    latest_ma = sma(close, ma_len)

    direction = "flat"
    strength = "low"

    if latest_rsi < rsi_long_max and latest_close > latest_ma:
        direction = "long"
        strength = "high"
    elif latest_rsi > rsi_short_min and latest_close < latest_ma:
        direction = "short"
        strength = "high"

    return {
        "direction": direction,
        "strength": strength,
        "rsi": latest_rsi,
        "ma": latest_ma,
        "close": latest_close,
    }


def _current_drawdown(equity: float, peak: float) -> float:
    if peak <= 0:
        return 0.0
    return max(0.0, (peak - equity) / peak)


def _append_activity(state: dict, action: str, symbol: str, message: str, market: str = "futures") -> None:
    activities = state.setdefault("activities", [])
    activities.append(
        {
            "ts": _utc_now_iso(),
            "market": market,
            "action": action,
            "symbol": symbol,
            "message": message,
        }
    )
    if len(activities) > 200:
        del activities[:-200]


def _close_position(
    futures_exchange: ccxt.Exchange,
    symbol: str,
    pos: dict,
    dry_run: bool,
    log,
    reason: str,
    state: dict,
    current_price: float | None = None,
) -> bool:
    side = _position_side(pos)
    qty = _position_size(pos)
    if side not in {"long", "short"} or qty <= 0:
        return False

    entry = _position_entry(pos)
    price = float(current_price or 0.0)

    # Fallback to mark price if needed
    if price <= 0:
        mark_price = pos.get("markPrice")
        if isinstance(mark_price, (int, float)):
            price = float(mark_price)
        else:
            info = pos.get("info") or {}
            try:
                price = float(info.get("markPrice") or 0.0)
            except Exception:
                price = 0.0

    # Compute PnL %
    pnl_pct = None
    if entry > 0 and price > 0:
        if side == "long":
            pnl_pct = (price - entry) / entry
        else:
            pnl_pct = (entry - price) / entry

    close_side = "sell" if side == "long" else "buy"
    pnl_txt = f" pnl={pnl_pct * 100:.2f}%" if pnl_pct is not None else ""

    if dry_run:
        log.info("[DRY][%s] Close %s %s qty=%.6f%s", reason, symbol, side, qty, pnl_txt)
    else:
        log.info("[%s] Closing %s %s qty=%.6f%s", reason, symbol, side, qty, pnl_txt)
        try:
            _create_futures_market_order(
                futures_exchange,
                symbol=symbol,
                side=close_side,
                qty=qty,
                reduce_only=True,
                hold_side=side,
            )
        except Exception as exc:
            # Bitget: 22002 = "No position to close"
            if "22002" in str(exc):
                log.warning("[%s] %s already closed on exchange (22002), skipping", reason, symbol)
                return False
            raise

        log.info("[%s] Closed %s %s qty=%.6f%s", reason, symbol, side, qty, pnl_txt)

    msg = f"closed {side} qty={qty:.6f}"
    if pnl_pct is not None:
        msg += f" pnl={pnl_pct * 100:.2f}%"

    _append_activity(state, action=f"CLOSE_{reason}", symbol=symbol, message=msg)
    return True


def _get_symbol_min_amount(
    symbol: str,
    market_limits_cache: dict[str, float],
    futures_exchange: ccxt.Exchange,
    log,
) -> float:
    """
    Get the minimum order amount (in base currency) for a symbol.
    Returns 0 if unable to fetch, allowing order to proceed anyway.
    """
    if symbol in market_limits_cache:
        return market_limits_cache[symbol]
    
    try:
        market = futures_exchange.market(symbol)
        limit_info = market.get("limits") or {}
        amount_info = limit_info.get("amount") or {}
        min_amount = float(amount_info.get("min") or 0.0)
        market_limits_cache[symbol] = min_amount
        if min_amount > 0:
            log.debug("[LIMITS] %s min_amount=%.6f", symbol, min_amount)
        return min_amount
    except Exception:
        # If we can't fetch limits, cache 0 to avoid repeated errors
        market_limits_cache[symbol] = 0.0
        return 0.0


def _get_symbol_min_notional(
    symbol: str,
    market_notional_cache: dict[str, float],
    futures_exchange: ccxt.Exchange,
    log,
) -> float:
    """
    Get the minimum order notional (in quote currency, usually USDT) for a symbol.
    Returns 0 if unavailable.
    """
    if symbol in market_notional_cache:
        return market_notional_cache[symbol]

    try:
        market = futures_exchange.market(symbol)
        limit_info = market.get("limits") or {}
        cost_info = limit_info.get("cost") or {}
        min_notional = float(cost_info.get("min") or 0.0)
        market_notional_cache[symbol] = min_notional
        if min_notional > 0:
            log.debug("[LIMITS] %s min_notional=%.6f", symbol, min_notional)
        return min_notional
    except Exception:
        market_notional_cache[symbol] = 0.0
        return 0.0

def _create_futures_market_order(
    futures_exchange: ccxt.Exchange,
    symbol: str,
    side: str,
    qty: float,
    reduce_only: bool,
    hold_side: str | None = None,
) -> dict:
    """
    Place Bitget futures market order with parameter fallbacks for both
    unilateral (one-way) and hedge position modes.
    """
    attempts: list[dict] = []

    # Attempt 1: minimal/unified params (works for many one-way setups)
    p1: dict[str, Any] = {}
    if reduce_only:
        p1["reduceOnly"] = True
    attempts.append(p1)

    # Attempt 2: explicit hedge-style params
    p2: dict[str, Any] = {
        "tradeSide": "close" if reduce_only else "open",
    }
    if reduce_only:
        p2["reduceOnly"] = True
    if hold_side in {"long", "short"}:
        p2["holdSide"] = hold_side
    attempts.append(p2)

    last_exc: Exception | None = None
    for params in attempts:
        try:
            return futures_exchange.create_order(symbol, "market", side, qty, params=params)
        except Exception as exc:
            last_exc = exc
            # Retry mode mismatch errors with next param style.
            if "40774" not in str(exc):
                raise

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Failed to place futures order: unknown error")

def run_futures_bot() -> None:
    cfg = load_config()
    fut_cfg = cfg.get("futures_bot", {})
    strat_cfg = cfg.get("futures_strategy", {})
    risk_cfg = cfg.get("futures_risk", {})
    funding_cfg = cfg.get("futures_funding", {})

    api_key = cfg.get("secrets", {}).get("bitget_api_key", "") or cfg.get("secrets", {}).get("api_key", "")
    api_secret = cfg.get("secrets", {}).get("bitget_api_secret", "") or cfg.get("secrets", {}).get("api_secret", "")
    api_passphrase = cfg.get("secrets", {}).get("bitget_api_passphrase", "")
    if not api_key or not api_secret or not api_passphrase:
        raise RuntimeError(
            "Missing API credentials. Set BITGET_API_KEY, BITGET_API_SECRET, and BITGET_API_PASSPHRASE in .env"
        )

    try:
        acquire_single_instance_lock("state/futures_bot.lock")
    except AlreadyRunningError:
        print("Another futures bot instance is already running. Exiting.")
        return

    log_level = str(fut_cfg.get("log_level", "INFO"))
    log = setup_logger(log_level, log_file="logs/futures_bot.log")

    futures_exchange = _build_exchange(
        api_key,
        api_secret,
        api_passphrase,
        str(fut_cfg.get("base_url", "")),
        default_type="swap",
    )
    try:
        futures_exchange.load_markets()
    except Exception as exc:
        log.warning("Could not preload futures markets: %s", exc)

    market_limits: dict[str, float] = {}
    market_min_notional: dict[str, float] = {}

    spot_exchange = None
    if bool(funding_cfg.get("enable_spot_hedge", False)):
        spot_exchange = _build_exchange(
            api_key,
            api_secret,
            api_passphrase,
            str(fut_cfg.get("base_url", "")),
            default_type="spot",
        )

    symbols = list(fut_cfg.get("pairs", []))
    if not symbols:
        raise RuntimeError("No futures pairs configured in [futures_bot].pairs")

    timeframe = str(fut_cfg.get("timeframe", "15m"))
    cycle_seconds = int(fut_cfg.get("cycle_seconds", 300))
    dry_run = bool(fut_cfg.get("dry_run", True))
    max_leverage = min(5, max(1, int(fut_cfg.get("max_leverage", 3))))

    risk_per_trade = float(risk_cfg.get("risk_per_trade", 0.01))
    # Bitget FUTURES minimum: 0.01 USDT
    # Safety margin: default 0.1 USDT (10x minimum) for slippage tolerance
    min_order_notional_usdt = float(risk_cfg.get("min_order_notional_usdt", 0.1))
    max_total_exposure = float(risk_cfg.get("max_total_exposure", 0.80))
    max_asset_exposure = float(risk_cfg.get("max_asset_exposure", 0.25))
    stop_loss_pct = float(risk_cfg.get("stop_loss_pct", 0.01))
    take_profit_pct = float(risk_cfg.get("take_profit_pct", 0.03))
    max_drawdown_pause_pct = float(risk_cfg.get("max_drawdown_pause_pct", 0.05))
    auto_close_on_drawdown_pause = bool(risk_cfg.get("auto_close_on_drawdown_pause", True))
    auto_close_on_signal_flip = bool(risk_cfg.get("auto_close_on_signal_flip", True))
    auto_close_wrong_direction_only_if_negative = bool(
        risk_cfg.get("auto_close_wrong_direction_only_if_negative", True)
    )

    funding_threshold = float(funding_cfg.get("funding_threshold", 0.0005))
    funding_exit_threshold = float(funding_cfg.get("funding_exit_threshold", 0.0002))

    state = load_futures_state()
    state.setdefault("meta", {}).setdefault("cycle", 0)
    state.setdefault("meta", {}).setdefault("paused", False)
    state.setdefault("meta", {}).setdefault("pause_reason", "")
    state.setdefault("meta", {}).setdefault("risk_flattened", False)
    previous_dry_run_mode = state.setdefault("meta", {}).get("dry_run_mode")
    state["meta"]["dry_run_mode"] = dry_run
    state.setdefault("risk", {}).setdefault("equity_peak_usdt", 0.0)
    state.setdefault("risk", {}).setdefault("last_equity_usdt", 0.0)
    state.setdefault("hedges", {})
    state.setdefault("position_protection", {})
    state.setdefault("position_pnl_prev", {})
    state.setdefault("activities", [])

    if previous_dry_run_mode is not None and bool(previous_dry_run_mode) != dry_run:
        state["meta"]["paused"] = False
        state["meta"]["pause_reason"] = ""
        state["meta"]["risk_flattened"] = False
        state["risk"]["equity_peak_usdt"] = 0.0
        state["risk"]["last_equity_usdt"] = 0.0
        _append_activity(
            state,
            action="MODE_SWITCH_RESET",
            symbol="ALL",
            message=f"risk state reset after dry_run={previous_dry_run_mode} -> dry_run={dry_run}",
        )

    log.info(
        "✅ Futures bot started. dry_run=%s timeframe=%s cycle=%ss max_leverage=%sx",
        dry_run,
        timeframe,
        cycle_seconds,
        max_leverage,
    )
    if previous_dry_run_mode is not None and bool(previous_dry_run_mode) != dry_run:
        log.info(
            "[MODE_SWITCH] Reset persisted risk state after dry_run=%s -> dry_run=%s",
            previous_dry_run_mode,
            dry_run,
        )

    while True:
        cycle_start = time.time()
        state["meta"]["cycle"] = int(state["meta"].get("cycle", 0)) + 1

        try:
            equity_total, equity_free = _fetch_balance_usdt(futures_exchange)
            state["risk"]["last_equity_usdt"] = equity_total
            state["risk"]["equity_peak_usdt"] = max(float(state["risk"].get("equity_peak_usdt", 0.0)), equity_total)

            dd = _current_drawdown(equity_total, float(state["risk"].get("equity_peak_usdt", 0.0)))
            if dd >= max_drawdown_pause_pct:
                state["meta"]["paused"] = True
                state["meta"]["pause_reason"] = f"drawdown {dd:.2%} >= {max_drawdown_pause_pct:.2%}"
                if auto_close_on_drawdown_pause and not bool(state["meta"].get("risk_flattened", False)):
                    positions_to_close = _fetch_positions_map(futures_exchange)
                    for sym_to_close, pos_to_close in positions_to_close.items():
                        _close_position(
                            futures_exchange,
                            sym_to_close,
                            pos_to_close,
                            dry_run,
                            log,
                            reason="RISK_DRAWDOWN",
                            state=state,
                        )
                    state["meta"]["risk_flattened"] = True
                    _append_activity(
                        state,
                        action="RISK_PAUSE",
                        symbol="ALL",
                        message=state["meta"]["pause_reason"],
                    )
            else:
                state["meta"]["paused"] = False
                state["meta"]["pause_reason"] = ""
                state["meta"]["risk_flattened"] = False

            drawdown_paused = bool(state["meta"].get("paused"))
            if drawdown_paused:
                log.warning("[RISK] Drawdown guard active (entry paused, managing exits): %s", state["meta"].get("pause_reason", ""))

            positions_map = _fetch_positions_map(futures_exchange, symbols)
            total_notional = sum(_position_notional(p) for p in positions_map.values())
            pnl_prev_map = state.setdefault("position_pnl_prev", {})
            managed_symbols = list(dict.fromkeys(symbols + list(positions_map.keys())))

            for symbol in managed_symbols:
                ohlcv = futures_exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=120)
                if not ohlcv or len(ohlcv) < 60:
                    continue

                df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
                signal = _compute_signal(df, strat_cfg)
                price = float(signal["close"])

                funding_rate = 0.0
                try:
                    fr = futures_exchange.fetch_funding_rate(symbol)
                    funding_rate = float(fr.get("fundingRate") or 0.0)
                except Exception:
                    pass

                pos = positions_map.get(symbol)
                current_notional = _position_notional(pos) if pos else 0.0
                current_side = _position_side(pos) if pos else ""
                pnl_pct = None
                prev_pnl_pct = pnl_prev_map.get(symbol)

                if pos and price > 0:
                    entry = _position_entry(pos)
                    if entry > 0:
                        if current_side == "long":
                            pnl_pct = (price - entry) / entry
                        elif current_side == "short":
                            pnl_pct = (entry - price) / entry
                        else:
                            pnl_pct = 0.0

                        if pnl_pct is not None:
                            pnl_prev_map[symbol] = float(pnl_pct)

                        # Keep explicit SL/TP setup in state for every open futures position.
                        if current_side == "long":
                            sl_price = entry * (1.0 - stop_loss_pct)
                            tp_price = entry * (1.0 + take_profit_pct)
                        else:
                            sl_price = entry * (1.0 + stop_loss_pct)
                            tp_price = entry * (1.0 - take_profit_pct)

                        protection = state.setdefault("position_protection", {})
                        prev_prot = protection.get(symbol) or {}
                        protection[symbol] = {
                            "symbol": symbol,
                            "side": current_side,
                            "entry": entry,
                            "sl": sl_price,
                            "tp": tp_price,
                            "updated_at": _utc_now_iso(),
                        }
                        if (
                            not prev_prot
                            or prev_prot.get("side") != current_side
                            or abs(float(prev_prot.get("entry", 0.0)) - entry) > 1e-12
                        ):
                            _append_activity(
                                state,
                                action="PROTECTION_SET",
                                symbol=symbol,
                                message=f"side={current_side} sl={sl_price:.6f} tp={tp_price:.6f}",
                            )

                        should_close = pnl_pct <= -stop_loss_pct or pnl_pct >= take_profit_pct
                        if should_close:
                            reason = "SL" if pnl_pct <= -stop_loss_pct else "TP"
                            _close_position(
                                futures_exchange,
                                symbol,
                                pos,
                                dry_run,
                                log,
                                reason=reason,
                                state=state,
                                current_price=price,
                            )
                            _append_activity(
                                state,
                                action=f"EXIT_{reason}",
                                symbol=symbol,
                                message=f"pnl={pnl_pct * 100:.2f}%",
                            )
                            continue

                if signal["direction"] in {"long", "short"} and equity_total > 0:
                    desired_side = signal["direction"]
                    if desired_side == current_side:
                        pass
                    else:
                        if pos and current_side and desired_side != current_side and auto_close_on_signal_flip:
                            pnl_improving = (
                                pnl_pct is not None and prev_pnl_pct is not None and float(pnl_pct) > float(prev_pnl_pct)
                            )
                            allow_close = not pnl_improving

                            # For the first opposite-signal observation, optionally require negative pnl.
                            if prev_pnl_pct is None and auto_close_wrong_direction_only_if_negative:
                                allow_close = (pnl_pct is not None and pnl_pct < 0.0)

                            if allow_close:
                                _close_position(
                                    futures_exchange,
                                    symbol,
                                    pos,
                                    dry_run,
                                    log,
                                    reason="SIGNAL_FLIP",
                                    state=state,
                                    current_price=price,
                                )
                                pnl_prev_map.pop(symbol, None)
                                total_notional = max(0.0, total_notional - current_notional)
                            else:
                                log.info(
                                    "[RISK] Keep %s %s; opposite signal but pnl improving (prev=%.2f%% now=%.2f%%)",
                                    current_side,
                                    symbol,
                                    (prev_pnl_pct or 0.0) * 100.0,
                                    (pnl_pct or 0.0) * 100.0,
                                )
                            continue

                        if drawdown_paused and not pos:
                            log.info("[RISK] Skip OPEN %s %s while drawdown guard is active", desired_side.upper(), symbol)
                            continue

                        target_notional = equity_total * risk_per_trade * max_leverage
                        max_by_asset = equity_total * max_asset_exposure
                        target_notional = min(target_notional, max_by_asset)

                        if (total_notional + target_notional) > (equity_total * max_total_exposure):
                            log.info("[RISK] Skip %s %s due to total exposure cap", desired_side.upper(), symbol)
                        else:
                            qty = target_notional / max(price, 1e-9)
                            try:
                                qty = float(futures_exchange.amount_to_precision(symbol, qty))
                            except Exception:
                                qty = float(qty)

                            min_amount = _get_symbol_min_amount(symbol, market_limits, futures_exchange, log)
                            min_notional_from_market = _get_symbol_min_notional(
                                symbol,
                                market_min_notional,
                                futures_exchange,
                                log,
                            )
                            effective_min_notional = max(min_order_notional_usdt, min_notional_from_market)
                            order_notional = qty * price
                            opened = False
                            if qty <= 0:
                                log.info("[LIMITS] Skip %s %s qty=%.6f (rounded to zero)", desired_side.upper(), symbol, qty)
                            elif min_amount > 0 and qty < min_amount:
                                log.info(
                                    "[LIMITS] Skip %s %s qty=%.6f < min_amount=%.6f",
                                    desired_side.upper(), symbol, qty, min_amount,
                                )
                            elif order_notional < effective_min_notional:
                                log.info(
                                    "[LIMITS] Skip %s %s notional=%.4f < min_notional=%.4f",
                                    desired_side.upper(), symbol, order_notional, effective_min_notional,
                                )
                            else:
                                side = "buy" if desired_side == "long" else "sell"
                                if dry_run:
                                    log.info(
                                        "[DRY] Open %s %s qty=%.6f price=%.6f rsi=%.2f funding=%.5f",
                                        desired_side.upper(), symbol, qty, price, signal["rsi"], funding_rate,
                                    )
                                else:
                                    try:
                                        futures_exchange.set_leverage(max_leverage, symbol)
                                    except Exception:
                                        pass
                                    hold_side = "long" if desired_side == "long" else "short"
                                    try:
                                        _create_futures_market_order(
                                            futures_exchange,
                                            symbol=symbol,
                                            side=side,
                                            qty=qty,
                                            reduce_only=False,
                                            hold_side=hold_side,
                                        )
                                    except Exception as exc:
                                        # Bitget 45110: less than minimum amount (USDT notional).
                                        if "45110" in str(exc):
                                            log.warning(
                                                "[LIMITS] Skip %s %s due to exchange min notional (45110), qty=%.6f notional=%.4f. Full error: %s",
                                                desired_side.upper(), symbol, qty, order_notional, str(exc),
                                            )
                                            continue
                                        raise
                                    log.info(
                                        "Open %s %s qty=%.6f price=%.6f rsi=%.2f funding=%.5f",
                                        desired_side.upper(), symbol, qty, price, signal["rsi"], funding_rate,
                                    )
                                opened = True

                            if opened:
                                _append_activity(
                                    state,
                                    action=f"OPEN_{desired_side.upper()}",
                                    symbol=symbol,
                                    message=f"qty={qty:.6f} price={price:.6f}",
                                )

                if abs(funding_rate) >= funding_threshold:
                    hedge_key = symbol
                    has_hedge = hedge_key in state["hedges"]
                    if not has_hedge and bool(funding_cfg.get("enabled", True)):
                        hedge_notional = equity_total * float(funding_cfg.get("allocation", 0.20))
                        hedge_qty = hedge_notional / max(price, 1e-9)
                        try:
                            hedge_qty = float(futures_exchange.amount_to_precision(symbol, hedge_qty))
                        except Exception:
                            hedge_qty = float(hedge_qty)

                        min_amount = _get_symbol_min_amount(symbol, market_limits, futures_exchange, log)
                        min_notional_from_market = _get_symbol_min_notional(
                            symbol,
                            market_min_notional,
                            futures_exchange,
                            log,
                        )
                        effective_min_notional = max(min_order_notional_usdt, min_notional_from_market)
                        hedge_order_notional = hedge_qty * price
                        hedge_opened = False
                        if hedge_qty <= 0:
                            log.info("[LIMITS] Skip hedge %s qty=%.6f (rounded to zero)", symbol, hedge_qty)
                        elif min_amount > 0 and hedge_qty < min_amount:
                            log.info(
                                "[LIMITS] Skip hedge %s qty=%.6f < min_amount=%.6f",
                                symbol, hedge_qty, min_amount,
                            )
                        elif hedge_order_notional < effective_min_notional:
                            log.info(
                                "[LIMITS] Skip hedge %s notional=%.4f < min_notional=%.4f",
                                symbol, hedge_order_notional, effective_min_notional,
                            )
                        else:
                            if funding_rate > 0:
                                fut_side = "sell"
                                spot_side = "buy"
                                hedge_dir = "short_futures_long_spot"
                            else:
                                fut_side = "buy"
                                spot_side = "sell"
                                hedge_dir = "long_futures_short_spot"

                            if dry_run:
                                log.info("[DRY][HEDGE] %s %s qty=%.6f funding=%.5f", hedge_dir, symbol, hedge_qty, funding_rate)
                                state["hedges"][hedge_key] = {
                                    "created_at": _utc_now_iso(),
                                    "symbol": symbol,
                                    "direction": hedge_dir,
                                    "qty": hedge_qty,
                                }
                            else:
                                hedge_hold_side = "short" if fut_side == "sell" else "long"
                                try:
                                    _create_futures_market_order(
                                        futures_exchange,
                                        symbol=symbol,
                                        side=fut_side,
                                        qty=hedge_qty,
                                        reduce_only=False,
                                        hold_side=hedge_hold_side,
                                    )
                                except Exception as exc:
                                    if "45110" in str(exc):
                                        log.info(
                                            "[LIMITS] Skip hedge %s due to exchange min notional (45110), qty=%.6f notional=%.4f",
                                            symbol, hedge_qty, hedge_order_notional,
                                        )
                                        continue
                                    raise
                            if spot_exchange and bool(funding_cfg.get("enable_spot_hedge", False)):
                                spot_exchange.create_order(_spot_symbol_from_perp(symbol), "market", spot_side, hedge_qty)
                            state["hedges"][hedge_key] = {
                                "created_at": _utc_now_iso(),
                                "symbol": symbol,
                                "direction": hedge_dir,
                                "qty": hedge_qty,
                            }
                            log.info("[HEDGE] Opened %s %s qty=%.6f funding=%.5f", hedge_dir, symbol, hedge_qty, funding_rate)
                            hedge_opened = True

                        if hedge_opened:
                            _append_activity(
                                state,
                                action="HEDGE_OPEN",
                                symbol=symbol,
                                message=f"{hedge_dir} qty={hedge_qty:.6f} funding={funding_rate:.5f}",
                            )

                if abs(funding_rate) <= funding_exit_threshold and symbol in state["hedges"]:
                    hedge = state["hedges"][symbol]
                    qty = float(hedge.get("qty", 0.0))
                    direction = str(hedge.get("direction", ""))
                    if direction == "short_futures_long_spot":
                        fut_close_side = "buy"
                        spot_close_side = "sell"
                    else:
                        fut_close_side = "sell"
                        spot_close_side = "buy"

                    if dry_run:
                        log.info("[DRY][HEDGE] Close %s qty=%.6f funding=%.5f", symbol, qty, funding_rate)
                    else:
                        close_hold_side = "short" if fut_close_side == "buy" else "long"
                        _create_futures_market_order(
                            futures_exchange,
                            symbol=symbol,
                            side=fut_close_side,
                            qty=qty,
                            reduce_only=True,
                            hold_side=close_hold_side,
                        )
                        if spot_exchange and bool(funding_cfg.get("enable_spot_hedge", False)):
                            spot_exchange.create_order(_spot_symbol_from_perp(symbol), "market", spot_close_side, qty)
                        log.info("[HEDGE] Closed %s qty=%.6f funding=%.5f", symbol, qty, funding_rate)
                    state["hedges"].pop(symbol, None)
                    _append_activity(
                        state,
                        action="HEDGE_CLOSE",
                        symbol=symbol,
                        message=f"qty={qty:.6f} funding={funding_rate:.5f}",
                    )

            save_futures_state(state)
            log.info(
                "[HEARTBEAT] cycle=%s equity_total=%.6f equity_free=%.6f positions=%d activities=%d paused=%s",
                state.get("meta", {}).get("cycle", 0),
                float(state.get("risk", {}).get("last_equity_usdt", 0.0) or 0.0),
                float(equity_free or 0.0),
                len(positions_map),
                len(state.get("activities", [])),
                bool(state.get("meta", {}).get("paused", False)),
            )

        except Exception as exc:
            log.exception("Futures cycle failed: %s", exc)
            send_telegram_message(cfg, f"⚠️ Futures bot cycle failed: {exc}", log=log)
            save_futures_state(state)

        elapsed = time.time() - cycle_start
        sleep_for = max(1, cycle_seconds - int(elapsed))
        time.sleep(sleep_for)
