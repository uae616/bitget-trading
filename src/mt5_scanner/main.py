#!/usr/bin/env python3
"""
Selective MT5 metals / commodities scanner.

Usage examples:
  python -m src.mt5_scanner.main
  python -m src.mt5_scanner.main XAUUSD XAGUSD --debug
  python -m src.mt5_scanner.main --watch 300
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ..unified_scanner.indicators import adx, atr, sma
from ..unified_scanner.signal_scorer import score_signal
from ..core.notify import send_telegram_message

log = logging.getLogger("mt5_scanner")
STATE_PATH = _PROJECT_ROOT / "state" / "mt5_scanner_state.json"

_TIMEFRAME_ALIASES = {
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}

_TIMEFRAME_SECONDS = {
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}

_SYMBOL_ALIASES = {
    "NATGAS": ["NG", "NATGAS"],
    "NG": ["NG", "NATGAS"],
    "USOIL": ["USOUSD", "USOIL", "XTIUSD", "WTI", "WTICOUSD"],
    "USOUSD": ["USOUSD", "USOIL", "XTIUSD", "WTI", "WTICOUSD"],
    "UKOIL": ["UKOUSD", "UKOIL", "XBRUSD", "BRENT", "BCOUSD"],
    "UKOUSD": ["UKOUSD", "UKOIL", "XBRUSD", "BRENT", "BCOUSD"],
}


@dataclass
class TradePlan:
    entry: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    trailing: float | None
    risk: float


def _load_config() -> dict:
    cfg_path = _PROJECT_ROOT / "config.toml"
    if not cfg_path.exists():
        return {}
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]
    with open(cfg_path, "rb") as f:
        return tomllib.load(f)


def _load_mt5():
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise RuntimeError(
            "MetaTrader5 package is not installed. Run: .\\.venv\\Scripts\\pip install MetaTrader5"
        ) from exc
    return mt5


def _timeframe(mt5, raw: str):
    tf_name = _TIMEFRAME_ALIASES.get(str(raw).upper())
    if not tf_name or not hasattr(mt5, tf_name):
        raise ValueError(f"Unsupported timeframe: {raw}")
    return getattr(mt5, tf_name)


def _connect_mt5(cfg: dict):
    mt5 = _load_mt5()
    creds = cfg.get("mt5_credentials", {})
    terminal_path = os.getenv("MT5_TERMINAL_PATH") or creds.get("terminal_path") or None
    initialized = mt5.initialize(path=terminal_path) if terminal_path else mt5.initialize()
    if not initialized:
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    login = int(os.getenv("MT5_LOGIN") or creds.get("login") or 0)
    password = os.getenv("MT5_PASSWORD") or creds.get("password") or ""
    server = os.getenv("MT5_SERVER") or creds.get("server") or ""
    if login and password and server:
        if not mt5.login(login=login, password=password, server=server):
            last_error = mt5.last_error()
            mt5.shutdown()
            raise RuntimeError(f"MT5 login failed: {last_error}")
    return mt5


def _load_state() -> dict:
    STATE_PATH.parent.mkdir(exist_ok=True)
    if not STATE_PATH.exists():
        return {"history": [], "emitted": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"history": [], "emitted": {}}


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _fetch_rates(mt5, symbol: str, timeframe_name: str, bars: int) -> list:
    requested = symbol.upper()
    candidates = _SYMBOL_ALIASES.get(requested, [requested])
    resolved_symbol = None
    rates = None
    for candidate in candidates:
        rates = mt5.copy_rates_from_pos(candidate, _timeframe(mt5, timeframe_name), 0, bars)
        if rates is not None and len(rates) > 0:
            resolved_symbol = candidate
            break
    if rates is None or len(rates) == 0:
        return []
    if resolved_symbol and resolved_symbol != requested:
        log.info("Resolved MT5 symbol %s -> %s", requested, resolved_symbol)
    klines = []
    for row in rates:
        klines.append([
            int(row["time"]),
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
            float(row.get("tick_volume", 0.0) if hasattr(row, "get") else row["tick_volume"]),
        ])
    return klines


def _session_open(cfg: dict, now_utc: datetime) -> bool:
    scanner_cfg = cfg.get("mt5_scanner", {})
    if not bool(scanner_cfg.get("use_trading_hours_filter", False)):
        return True
    start_hour = int(scanner_cfg.get("trade_hours_utc_start", 0))
    end_hour = int(scanner_cfg.get("trade_hours_utc_end", 24))
    if now_utc.weekday() >= 5:
        return False
    return start_hour <= now_utc.hour < end_hour


def _is_stale(klines: list, timeframe_name: str, now_utc: datetime, tolerance_bars: float) -> bool:
    if not klines:
        return True
    tf_seconds = _TIMEFRAME_SECONDS[timeframe_name.upper()]
    allowed_age = tf_seconds * max(1.0, float(tolerance_bars))
    latest_bar_ts = int(klines[-1][0])
    age_seconds = now_utc.timestamp() - latest_bar_ts
    return age_seconds > allowed_age


def _count_today_signals(state: dict, now_utc: datetime) -> int:
    today = now_utc.date().isoformat()
    history = state.get("history", [])
    return sum(1 for item in history if str(item.get("date", "")) == today)


def _remember_signal(state: dict, symbol: str, direction: str, bar_time: int, score: int, confidence: float) -> None:
    state.setdefault("emitted", {})[symbol.upper()] = {
        "direction": direction,
        "bar_time": int(bar_time),
    }
    history = state.setdefault("history", [])
    now_utc = datetime.now(timezone.utc)
    history.append(
        {
            "ts": now_utc.isoformat(),
            "date": now_utc.date().isoformat(),
            "symbol": symbol.upper(),
            "direction": direction,
            "bar_time": int(bar_time),
            "score": int(score),
            "confidence": float(confidence),
        }
    )
    if len(history) > 500:
        state["history"] = history[-500:]


def _cooldown_active(state: dict, symbol: str, bar_time: int, timeframe_name: str, cooldown_bars: int) -> bool:
    if cooldown_bars <= 0:
        return False
    last = state.get("emitted", {}).get(symbol.upper())
    if not last:
        return False
    min_seconds = _TIMEFRAME_SECONDS[timeframe_name.upper()] * cooldown_bars
    return (int(bar_time) - int(last.get("bar_time", 0))) < min_seconds


def _build_trade_plan(klines: list, direction: str, cfg: dict) -> TradePlan:
    scanner_cfg = cfg.get("mt5_scanner", {})
    closes = [float(k[4]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    entry = closes[-1]
    atr_val = atr(highs, lows, closes, 14)
    risk = atr_val * 1.5 if atr_val > 0 else entry * 0.008
    trailing = entry - atr_val if direction == "BUY" and atr_val > 0 else None
    if direction == "SELL" and atr_val > 0:
        trailing = entry + atr_val
    rr1 = float(scanner_cfg.get("rr_tp1", 1.0))
    rr2 = float(scanner_cfg.get("rr_tp2", 1.5))
    rr3 = float(scanner_cfg.get("rr_tp3", 2.2))

    if direction == "BUY":
        stop_loss = entry - risk
        tp1 = entry + risk * rr1
        tp2 = entry + risk * rr2
        tp3 = entry + risk * rr3
    else:
        stop_loss = entry + risk
        tp1 = entry - risk * rr1
        tp2 = entry - risk * rr2
        tp3 = entry - risk * rr3

    return TradePlan(
        entry=round(entry, 5),
        stop_loss=round(stop_loss, 5),
        tp1=round(tp1, 5),
        tp2=round(tp2, 5),
        tp3=round(tp3, 5),
        trailing=round(trailing, 5) if trailing is not None else None,
        risk=round(risk, 5),
    )


def _qualifies(symbol: str, primary_sig, confirm_sig, trend_klines: list, primary_klines: list, cfg: dict) -> tuple[bool, list[str]]:
    scanner_cfg = cfg.get("mt5_scanner", {})
    reasons = []
    min_primary_score = int(scanner_cfg.get("min_primary_score", 8))
    min_confirm_score = int(scanner_cfg.get("min_confirm_score", 6))
    min_confidence = float(scanner_cfg.get("min_confidence", 0.66))
    min_adx = float(scanner_cfg.get("min_adx", 22.0))
    trend_ma_len = int(scanner_cfg.get("trend_ma_len", 50))

    if primary_sig.direction == "HOLD":
        return False, ["primary timeframe is HOLD"]
    if primary_sig.score < min_primary_score:
        return False, [f"primary score {primary_sig.score} < {min_primary_score}"]
    if primary_sig.confidence < min_confidence:
        return False, [f"confidence {primary_sig.confidence:.0%} < {min_confidence:.0%}"]
    if confirm_sig.direction != primary_sig.direction:
        return False, [f"confirm timeframe disagrees ({confirm_sig.direction})"]
    if confirm_sig.score < min_confirm_score:
        return False, [f"confirm score {confirm_sig.score} < {min_confirm_score}"]

    highs = [float(k[2]) for k in primary_klines]
    lows = [float(k[3]) for k in primary_klines]
    closes = [float(k[4]) for k in primary_klines]
    adx_val = adx(highs, lows, closes, 14)
    if adx_val < min_adx:
        return False, [f"ADX {adx_val:.1f} < {min_adx:.1f}"]

    trend_closes = [float(k[4]) for k in trend_klines]
    if len(trend_closes) < trend_ma_len:
        return False, ["insufficient trend timeframe data"]
    trend_sma = sma(trend_closes, trend_ma_len)
    trend_last = trend_closes[-1]
    if primary_sig.direction == "BUY" and trend_last <= trend_sma:
        return False, [f"trend filter bearish ({trend_last:.5f} <= {trend_sma:.5f})"]
    if primary_sig.direction == "SELL" and trend_last >= trend_sma:
        return False, [f"trend filter bullish ({trend_last:.5f} >= {trend_sma:.5f})"]

    reasons.extend(
        [
            f"primary {primary_sig.direction} score={primary_sig.score}/{primary_sig.max_score}",
            f"confirm {confirm_sig.direction} score={confirm_sig.score}/{confirm_sig.max_score}",
            f"ADX {adx_val:.1f}",
        ]
    )
    return True, reasons


def _print_signal(symbol: str, direction: str, primary_sig, confirm_sig, plan: TradePlan, reasons: list[str]) -> None:
    print(
        f"{symbol:>8}  {direction:>4}  primary={primary_sig.score}/{primary_sig.max_score}  "
        f"confirm={confirm_sig.score}/{confirm_sig.max_score}  conf={primary_sig.confidence:.0%}"
    )
    print(
        f"          entry={plan.entry}  sl={plan.stop_loss}  "
        f"TP1={plan.tp1}  TP2={plan.tp2}  TP3={plan.tp3}"
    )
    if plan.trailing is not None:
        print(f"          trailing={plan.trailing}  risk={plan.risk}")
    if reasons:
        for item in reasons:
            print(f"          - {item}")


def _format_telegram_message(symbol: str, direction: str, primary_sig, confirm_sig, plan: TradePlan, reasons: list[str]) -> str:
    emoji = "🟢" if direction == "BUY" else "🔴"
    lines = [
        f"{emoji} *MT5 Signal: {direction} {symbol}*",
        f"Primary: {primary_sig.score}/{primary_sig.max_score}  Confirm: {confirm_sig.score}/{confirm_sig.max_score}  Conf: {primary_sig.confidence:.0%}",
        f"Entry: `{plan.entry}`  SL: `{plan.stop_loss}`",
        f"TP1: `{plan.tp1}`  TP2: `{plan.tp2}`  TP3: `{plan.tp3}`",
    ]
    if plan.trailing is not None:
        lines.append(f"Trailing: `{plan.trailing}`  Risk: `{plan.risk}`")
    if reasons:
        lines.append("• " + "  • ".join(reasons))
    return "\n".join(lines)


def _scan_once(args, cfg: dict | None = None) -> int:
    if cfg is None:
        cfg = _load_config()
    scanner_cfg = cfg.get("mt5_scanner", {})
    symbols = [str(s).upper() for s in (args.symbols or scanner_cfg.get("symbols", []))]
    if not symbols:
        raise RuntimeError("No symbols configured for mt5_scanner")

    now_utc = datetime.now(timezone.utc)
    if not _session_open(cfg, now_utc):
        print("MT5 scanner skipped: outside configured UTC trading window.")
        return 0

    state = _load_state()
    daily_cap = int(scanner_cfg.get("max_signals_per_day", 6))
    todays_count = _count_today_signals(state, now_utc)
    cooldown_bars = int(scanner_cfg.get("signal_cooldown_bars", 8))
    bars = int(scanner_cfg.get("bars", 240))
    primary_tf = str(scanner_cfg.get("primary_timeframe", "M15")).upper()
    confirm_tf = str(scanner_cfg.get("confirm_timeframe", "H1")).upper()
    trend_tf = str(scanner_cfg.get("trend_timeframe", "H4")).upper()
    stale_tolerance_bars = float(scanner_cfg.get("stale_candle_tolerance_bars", 2.2))

    mt5 = _connect_mt5(cfg)
    emitted = 0

    try:
        for symbol in symbols:
            primary_klines = _fetch_rates(mt5, symbol, primary_tf, bars)
            confirm_klines = _fetch_rates(mt5, symbol, confirm_tf, max(120, bars // 2))
            trend_klines = _fetch_rates(mt5, symbol, trend_tf, max(120, bars // 4))
            if not primary_klines or not confirm_klines or not trend_klines:
                if args.debug:
                    print(f"{symbol}: skipped (missing MT5 data)")
                continue
            if _is_stale(primary_klines, primary_tf, now_utc, stale_tolerance_bars):
                if args.debug:
                    print(f"{symbol}: skipped (stale {primary_tf} candles)")
                continue
            if _is_stale(confirm_klines, confirm_tf, now_utc, stale_tolerance_bars):
                if args.debug:
                    print(f"{symbol}: skipped (stale {confirm_tf} candles)")
                continue
            if _is_stale(trend_klines, trend_tf, now_utc, stale_tolerance_bars):
                if args.debug:
                    print(f"{symbol}: skipped (stale {trend_tf} candles)")
                continue

            # Build a scorer config that inherits [scanner] defaults but applies
            # MT5-specific ADX threshold and score minimum so metals are not
            # penalised by the Bitget-tuned [scanner] ADX floor (20) in Asian session.
            scorer_cfg = dict(cfg.get("scanner", {}))
            scorer_cfg["adx_min"] = float(scanner_cfg.get("min_adx", scorer_cfg.get("adx_min", 20.0)))
            scorer_cfg["min_score_for_signal"] = max(1, int(scanner_cfg.get("min_primary_score", 6)) - 1)
            # Confirm timeframe (H1) uses a lower scoring threshold so it can
            # produce a directional opinion even with fewer aligned indicators.
            confirm_scorer_cfg = dict(scorer_cfg)
            confirm_scorer_cfg["min_score_for_signal"] = max(1, int(scanner_cfg.get("min_confirm_score", 4)) - 1)
            primary_sig = score_signal(primary_klines, scorer_cfg)
            confirm_sig = score_signal(confirm_klines, confirm_scorer_cfg)
            ok, reasons = _qualifies(symbol, primary_sig, confirm_sig, trend_klines, primary_klines, cfg)
            if not ok:
                if args.debug:
                    print(f"{symbol}: HOLD ({'; '.join(reasons)})")
                continue

            bar_time = int(primary_klines[-1][0])
            if _cooldown_active(state, symbol, bar_time, primary_tf, cooldown_bars):
                if args.debug:
                    print(f"{symbol}: cooldown active")
                continue
            if todays_count + emitted >= daily_cap:
                if args.debug:
                    print(f"{symbol}: daily cap reached ({daily_cap})")
                continue

            plan = _build_trade_plan(primary_klines, primary_sig.direction, cfg)
            _print_signal(symbol, primary_sig.direction, primary_sig, confirm_sig, plan, reasons)
            _remember_signal(state, symbol, primary_sig.direction, bar_time, primary_sig.score, primary_sig.confidence)
            # Send Telegram notification
            tg_msg = _format_telegram_message(symbol, primary_sig.direction, primary_sig, confirm_sig, plan, reasons)
            send_telegram_message(cfg, tg_msg, log=log)
            emitted += 1

        _save_state(state)
    finally:
        mt5.shutdown()

    if emitted == 0 and not args.debug:
        print("No new MT5 metals/commodities signals matched the strict filters.")
    return emitted


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mt5_scanner",
        description="Selective MT5 metals / commodities scanner with TP1/TP2/TP3 output.",
    )
    parser.add_argument("symbols", nargs="*", default=None, help="Override configured symbols")
    parser.add_argument("--watch", type=int, default=None, metavar="SECS", help="Re-scan every N seconds")
    parser.add_argument("--debug", action="store_true", help="Explain why symbols are filtered out")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("mt5_scanner").setLevel(logging.DEBUG if args.debug else logging.INFO)

    cfg = _load_config()
    # Use --watch value, else fall back to watch_seconds in config (default 300)
    watch_secs = args.watch if args.watch is not None else int(cfg.get("mt5_scanner", {}).get("watch_seconds", 300))

    print(f"MT5 scanner live — scanning every {watch_secs}s. Press Ctrl+C to stop.")
    while True:
        try:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] MT5 scan")
            _scan_once(args, cfg=cfg)
        except KeyboardInterrupt:
            print("Stopped.")
            break
        except Exception as exc:
            print(f"Scanner error: {exc}")
        time.sleep(watch_secs)


if __name__ == "__main__":
    main()
