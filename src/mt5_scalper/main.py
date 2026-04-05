from __future__ import annotations

import time
from datetime import datetime

from ..core.logger import setup_logger
from ..core.settings import load_config
from .state import load_state, save_state, add_activity
from .strategy import compute_signal


_TIMEFRAME_MAP = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
}

_PIP_MULTIPLIER = {
    "XAUUSD": 0.10,  # 50 pips = 5.00 price movement
    "XAGUSD": 0.10,  # 50 pips = 5.00 price movement
}


def _load_mt5():
    import MetaTrader5 as mt5
    return mt5


def _timeframe_const(mt5, tf: str):
    name = f"TIMEFRAME_{tf.upper()}"
    if not hasattr(mt5, name):
        raise ValueError(f"Unsupported timeframe: {tf}")
    return getattr(mt5, name)


def _pip_multiplier(symbol: str) -> float:
    return float(_PIP_MULTIPLIER.get(symbol.upper(), 0.0001))


def run_mt5_scalper(once: bool = False) -> None:
    from .risk import get_safe_volume, get_volume_info
    
    cfg = load_config()
    scalper_cfg = cfg.get("mt5_scalper", {})

    log = setup_logger(str(scalper_cfg.get("log_level", "INFO")), log_file="logs/mt5_scalper.log")
    state = load_state()
    signal_meta = state.setdefault("meta", {}).setdefault("signal_meta", {})
    positions = state.setdefault("positions", {})

    symbols = [str(s).upper() for s in scalper_cfg.get("symbols", ["XAUUSD", "XAGUSD"])]
    timeframe = str(scalper_cfg.get("timeframe", "M5"))
    bars = int(scalper_cfg.get("bars", 200))
    cycle_seconds = int(scalper_cfg.get("cycle_seconds", 60))
    dry_run = bool(scalper_cfg.get("dry_run", True))
    position_size = float(scalper_cfg.get("position_size", 0.01))
    sl_pips = float(scalper_cfg.get("stop_loss_pips", 20))
    tp_pips = float(scalper_cfg.get("take_profit_pips", 40))
    raw_overrides = scalper_cfg.get("symbol_overrides", {})
    symbol_overrides = {
        str(k).upper(): v for k, v in raw_overrides.items() if isinstance(v, dict)
    }
    
    # Dynamic position sizing
    use_dynamic_sizing = bool(scalper_cfg.get("use_dynamic_sizing", True))
    account_balance = float(scalper_cfg.get("account_balance", 5000))
    risk_percent = float(scalper_cfg.get("risk_percent", 1.0))
    
    # Calculate dynamic position size if enabled
    if use_dynamic_sizing:
        # Convert pips to dollars for SL distance
        sl_dist_dollars = sl_pips * _pip_multiplier("XAGUSD")  # Using silver as reference
        try:
            dynamic_position_size = get_safe_volume(account_balance, risk_percent, sl_dist_dollars)
            log.info("Dynamic position sizing: account_balance=$%.2f risk=%.1f%% → position_size=%.2f lots",
                    account_balance, risk_percent, dynamic_position_size)
            position_size = dynamic_position_size
        except ValueError as e:
            log.warning("Dynamic position sizing failed (%s), using fallback: %.2f lots", str(e), position_size)

    mt5 = _load_mt5()

    creds = cfg.get("mt5_credentials", {})
    terminal_path = creds.get("terminal_path") or None
    if terminal_path:
        ok_init = mt5.initialize(path=terminal_path)
    else:
        ok_init = mt5.initialize()
    if not ok_init:
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    login = int(creds.get("login") or 0)
    password = str(creds.get("password") or "")
    server = str(creds.get("server") or "")
    if login and password and server:
        if not mt5.login(login=login, password=password, server=server):
            err = mt5.last_error()
            mt5.shutdown()
            raise RuntimeError(f"MT5 login failed: {err}")

    log.info("MT5 scalper started. dry_run=%s timeframe=%s cycle=%ss position_size=%s SL=%spips TP=%spips", 
             dry_run, timeframe, cycle_seconds, position_size, sl_pips, tp_pips)

    try:
        while True:
            state.setdefault("meta", {})["cycle"] = int(state.get("meta", {}).get("cycle", 0)) + 1
            tf_const = _timeframe_const(mt5, timeframe)

            for symbol in symbols:
                symbol_cfg = symbol_overrides.get(symbol, {})
                symbol_sl_pips = float(symbol_cfg.get("stop_loss_pips", sl_pips))
                symbol_tp_pips = float(symbol_cfg.get("take_profit_pips", tp_pips))
                pip_multiplier = _pip_multiplier(symbol)

                rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, bars)
                if rates is None or len(rates) < 50:
                    add_activity(state, "SKIP", symbol, "missing_or_short_rates")
                    continue

                ohlcv = [[int(r["time"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["tick_volume"])] for r in rates]
                bar_time = int(ohlcv[-1][0])
                current_price = float(ohlcv[-1][4])
                sig = compute_signal(ohlcv, symbol)

                # Calculate unrealized P&L for open positions
                if symbol in positions:
                    pos = positions[symbol]
                    pos_pip_multiplier = float(pos.get("pip_multiplier", pip_multiplier))
                    if pos["direction"] == "BUY":
                        unrealized_pnl = (current_price - pos["entry_price"]) / pos_pip_multiplier
                    else:
                        unrealized_pnl = (pos["entry_price"] - current_price) / pos_pip_multiplier
                    pos["unrealized_pnl"] = unrealized_pnl
                    pos["current_price"] = current_price
                    
                    # Check exit conditions (TP/SL)
                    if pos["direction"] == "BUY":
                        if current_price >= pos["tp"]:
                            # Take profit hit
                            realized_pnl = (pos["tp"] - pos["entry_price"]) / pos_pip_multiplier
                            log.info("[CLOSE] %s BUY TP hit. Entry: %.2f → TP: %.2f | Realized P&L: +%.1f pips", 
                                   symbol, pos["entry_price"], pos["tp"], realized_pnl)
                            add_activity(state, "EXIT_BUY", symbol, f"TP_HIT entry={pos['entry_price']} exit={pos['tp']} pnl={realized_pnl:.1f}")
                            del positions[symbol]
                        elif current_price <= pos["sl"]:
                            # Stop loss hit
                            realized_pnl = (pos["sl"] - pos["entry_price"]) / pos_pip_multiplier
                            log.info("[CLOSE] %s BUY SL hit. Entry: %.2f → SL: %.2f | Realized P&L: %.1f pips", 
                                   symbol, pos["entry_price"], pos["sl"], realized_pnl)
                            add_activity(state, "EXIT_BUY", symbol, f"SL_HIT entry={pos['entry_price']} exit={pos['sl']} pnl={realized_pnl:.1f}")
                            del positions[symbol]
                    else:  # SELL
                        if current_price <= pos["tp"]:
                            # Take profit hit
                            realized_pnl = (pos["entry_price"] - pos["tp"]) / pos_pip_multiplier
                            log.info("[CLOSE] %s SELL TP hit. Entry: %.2f → TP: %.2f | Realized P&L: +%.1f pips", 
                                   symbol, pos["entry_price"], pos["tp"], realized_pnl)
                            add_activity(state, "EXIT_SELL", symbol, f"TP_HIT entry={pos['entry_price']} exit={pos['tp']} pnl={realized_pnl:.1f}")
                            del positions[symbol]
                        elif current_price >= pos["sl"]:
                            # Stop loss hit
                            realized_pnl = (pos["entry_price"] - pos["sl"]) / pos_pip_multiplier
                            log.info("[CLOSE] %s SELL SL hit. Entry: %.2f → SL: %.2f | Realized P&L: %.1f pips", 
                                   symbol, pos["entry_price"], pos["sl"], realized_pnl)
                            add_activity(state, "EXIT_SELL", symbol, f"SL_HIT entry={pos['entry_price']} exit={pos['sl']} pnl={realized_pnl:.1f}")
                            del positions[symbol]
                    continue

                if sig.direction == "HOLD":
                    continue

                prev = signal_meta.get(symbol, {})
                prev_bar = int(prev.get("bar_time", 0) or 0)
                prev_dir = str(prev.get("direction", ""))
                prev_reason = str(prev.get("reason", ""))

                # Avoid repeating the exact same signal every cycle on the same bar.
                if bar_time == prev_bar and sig.direction == prev_dir and sig.reason == prev_reason:
                    continue

                msg = f"signal={sig.direction} score={sig.score} conf={sig.confidence:.2f} reason={sig.reason}"
                
                if dry_run:
                    log.info("[DRY] %s %s", symbol, msg)
                    add_activity(state, f"SIGNAL_{sig.direction}", symbol, msg)
                    
                    # In dry run, simulate entry
                    if sig.direction == "BUY":
                        sl = current_price - (symbol_sl_pips * pip_multiplier)
                        tp = current_price + (symbol_tp_pips * pip_multiplier)
                    else:
                        sl = current_price + (symbol_sl_pips * pip_multiplier)
                        tp = current_price - (symbol_tp_pips * pip_multiplier)
                    
                    positions[symbol] = {
                        "direction": sig.direction,
                        "entry_price": current_price,
                        "sl": sl,
                        "tp": tp,
                        "size": position_size,
                        "pip_multiplier": pip_multiplier,
                        "unrealized_pnl": 0.0,
                        "current_price": current_price,
                        "entry_signal": sig.reason
                    }
                    log.info("[ENTRY] %s %s @ %.2f | SL: %.2f TP: %.2f", symbol, sig.direction, current_price, sl, tp)
                    add_activity(state, f"ENTRY_{sig.direction}", symbol, f"price={current_price} sl={sl} tp={tp}")
                else:
                    log.info("[LIVE] %s %s", symbol, msg)
                    add_activity(state, f"SIGNAL_{sig.direction}", symbol, msg)

                signal_meta[symbol] = {
                    "bar_time": bar_time,
                    "direction": sig.direction,
                    "reason": sig.reason,
                }

            save_state(state)
            log.info("[HEARTBEAT] cycle=%s symbols=%d open_positions=%d", 
                    state.get("meta", {}).get("cycle", 0), len(symbols), len(positions))

            if once:
                break
            time.sleep(max(1, cycle_seconds))
    finally:
        mt5.shutdown()


def main() -> None:
    run_mt5_scalper(once=False)


if __name__ == "__main__":
    main()
