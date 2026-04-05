#!/usr/bin/env python3
"""
Unified Signal Scanner — CLI entry point.

Usage examples:
  python -m src.unified_scanner.main BTC ETH SOL          # scan specific symbols
  python -m src.unified_scanner.main BTC --debug           # full debug dump
  python -m src.unified_scanner.main BTC ETH --verbose     # verbose output
  python -m src.unified_scanner.main --top 10              # scan top-10 by volume
  python -m src.unified_scanner.main BTC --interval 1h     # use 1h candles
  python -m src.unified_scanner.main BTC --backtest        # run backtest on klines
  python -m src.unified_scanner.main BTC --exchange bitget  # use bitget instead of binance
  python -m src.unified_scanner.main LYNUSDT --exchange bitget --market futures
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path so imports work when run standalone
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from .signal_scorer import score_signal, SignalResult
from .sl_tp import compute_sl_tp
from .backtest import run_backtest, backtest_summary
from .indicators import (
    rsi, macd, atr, bollinger_bands, stochastic, ichimoku,
    laguerre_rsi, hma, keltner_channel, rolling_vwap,
)

log = logging.getLogger("unified_scanner")

_STABLE_BASES = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "FDUSD", "USDE", "USD1", "PYUSD"
}


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load config.toml from project root (same logic as src.core.settings)."""
    cfg_path = _PROJECT_ROOT / "config.toml"
    if not cfg_path.exists():
        return {}
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]
    with open(cfg_path, "rb") as f:
        return tomllib.load(f)


# ---------------------------------------------------------------------------
# Exchange connection (ccxt)
# ---------------------------------------------------------------------------

def _connect_exchange(exchange_id: str = "binance", market: str = "spot") -> "ccxt.Exchange":
    """Create a public-only ccxt exchange instance."""
    import ccxt
    cls = getattr(ccxt, exchange_id, None)
    if cls is None:
        log.error("Exchange %r not supported by ccxt", exchange_id)
        sys.exit(1)
    opts = {"enableRateLimit": True}
    if market == "futures":
        default_type = "swap" if exchange_id in {"bitget", "bybit", "okx"} else "future"
        opts["options"] = {"defaultType": default_type}
    exchange = cls(opts)
    exchange.load_markets()
    return exchange


def _effective_market(exchange_id: str, market: str) -> str:
    if market != "auto":
        return market
    return "futures" if str(exchange_id).lower() == "bitget" else "spot"


def _resolve_pair(exchange, symbol: str, quote: str, market: str) -> str | None:
    base = symbol.upper()
    q = quote.upper()
    if market == "futures":
        candidates = [f"{base}/{q}:{q}", f"{base}/{q}"]
    else:
        candidates = [f"{base}/{q}"]
    for pair in candidates:
        if pair in exchange.markets:
            return pair
    return None


def _fetch_klines(exchange, symbol: str, quote: str, interval: str, limit: int, market: str = "spot") -> list:
    """Fetch OHLCV via ccxt. Returns list of [ts, open, high, low, close, vol]."""
    pair = _resolve_pair(exchange, symbol, quote, market)
    if not pair:
        req_pair = f"{symbol.upper()}/{quote.upper()}"
        log.warning("Pair %s not found on %s (%s) — skipping", req_pair, exchange.id, market)
        return []
    ohlcv = exchange.fetch_ohlcv(pair, timeframe=interval, limit=limit)
    return ohlcv


def _fetch_top_symbols(exchange, quote: str, top_n: int, market: str = "spot") -> list[str]:
    """Return top N symbols by 24h quote volume on the exchange."""
    tickers = exchange.fetch_tickers()
    candidates = []
    for sym, t in tickers.items():
        if market == "futures":
            if not sym.endswith(f"/{quote.upper()}:{quote.upper()}"):
                continue
        else:
            if not sym.endswith(f"/{quote.upper()}"):
                continue
        vol = t.get("quoteVolume") or 0
        base = sym.split("/")[0]
        candidates.append((base, vol))
    candidates.sort(key=lambda x: x[1], reverse=True)
    symbols: list[str] = []
    seen: set[str] = set()
    for base, _ in candidates:
        base_upper = base.upper()
        if base_upper in _STABLE_BASES or base_upper in seen:
            continue
        symbols.append(base)
        seen.add(base_upper)
        if len(symbols) >= top_n:
            break
    return symbols


def _fallback_symbols(cfg: dict) -> list[str]:
    scanner_symbols = cfg.get("scanner", {}).get("symbols", [])
    if scanner_symbols:
        return [str(s).upper() for s in scanner_symbols if str(s).upper() not in _STABLE_BASES]
    return [str(s).upper() for s in cfg.get("portfolio", {}).get("coins", ["BTC", "ETH", "SOL", "BNB"]) if str(s).upper() not in _STABLE_BASES]


def _normalize_symbol_input(raw: str, quote: str) -> str:
    s = str(raw).strip().upper()
    if not s:
        return s
    # Accept LINKUSDT, LINK/USDT, LINK-USDT and normalize to base symbol LINK.
    s = s.replace("-", "/")
    if "/" in s:
        base = s.split("/")[0]
    else:
        q = quote.upper()
        base = s[:-len(q)] if s.endswith(q) and len(s) > len(q) else s
    return base


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

_COLOR = {
    "BUY":  "\033[92m",  # green
    "SELL": "\033[91m",  # red
    "HOLD": "\033[90m",  # gray
    "RST":  "\033[0m",
    "BOLD": "\033[1m",
    "DIM":  "\033[2m",
    "CYAN": "\033[96m",
    "YLW":  "\033[93m",
}


def _should_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(tag: str) -> str:
    return _COLOR.get(tag, "") if _should_color() else ""


def _print_signal(symbol: str, sig: SignalResult, sl_tp=None, *, verbose: bool = False):
    d = sig.direction
    bar = "█" * sig.score + "░" * (sig.max_score - sig.score)
    header = (
        f"{_c('BOLD')}{symbol:>8}{_c('RST')}  "
        f"{_c(d)}{d:>4}{_c('RST')}  "
        f"[{bar}] {sig.score}/{sig.max_score}  "
        f"conf={sig.confidence:.0%}"
    )
    print(header)

    if verbose and sig.reasons:
        for r in sig.reasons:
            print(f"           {_c('DIM')}{r}{_c('RST')}")

    if verbose and sl_tp and d != "HOLD":
        print(
            f"           SL={sl_tp.stop_loss:.4f}  "
            f"TP={sl_tp.take_profit:.4f}  "
            f"trail={sl_tp.trailing_stop}  "
            f"({sl_tp.method})"
        )


def _print_debug(symbol: str, klines: list, sig: SignalResult, scanner_cfg: dict):
    """Full debug dump — all indicator values."""
    closes = [float(k[4]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    volumes = [float(k[5]) for k in klines]

    m = macd(closes)
    bb = bollinger_bands(closes)
    stoch = stochastic(highs, lows, closes)
    ichi = ichimoku(highs, lows, closes)
    kc = keltner_channel(highs, lows, closes)
    vwap = rolling_vwap(highs, lows, closes, volumes)
    hull = hma(closes)
    lrsi = laguerre_rsi(closes)

    print(f"\n{_c('CYAN')}{'=' * 60}")
    print(f"  DEBUG: {symbol}")
    print(f"{'=' * 60}{_c('RST')}")
    print(f"  Candles: {len(klines)}  |  Last close: {closes[-1]}")
    print()
    print(f"  {_c('YLW')}--- Core Indicators ---{_c('RST')}")
    print(f"  RSI(14)       = {sig.rsi:.2f}")
    print(f"  Laguerre RSI  = {lrsi:.4f}")
    print(f"  MACD line     = {m['macd_line']:.6f}")
    print(f"  MACD signal   = {m['signal']:.6f}")
    print(f"  MACD hist     = {m['histogram']:.6f}")
    print(f"  ATR(14)       = {sig.atr_val:.6f}")
    print(f"  SMA(50)       = {sig.sma_val:.4f}")
    print(f"  HMA(20)       = {hull:.4f}")
    print()
    print(f"  {_c('YLW')}--- Bands & Channels ---{_c('RST')}")
    print(f"  Bollinger     = upper={bb['upper']:.4f}  mid={bb['mid']:.4f}  lower={bb['lower']:.4f}  bw={bb['bandwidth']:.4f}")
    print(f"  Keltner       = upper={kc['upper']:.4f}  mid={kc['mid']:.4f}  lower={kc['lower']:.4f}")
    print(f"  VWAP(20)      = {vwap:.4f}")
    print()
    print(f"  {_c('YLW')}--- Oscillators ---{_c('RST')}")
    print(f"  Stochastic    = %K={stoch['k']:.2f}  %D={stoch['d']:.2f}")
    print()
    print(f"  {_c('YLW')}--- Ichimoku Cloud ---{_c('RST')}")
    print(f"  Tenkan        = {ichi['tenkan_sen']:.4f}")
    print(f"  Kijun         = {ichi['kijun_sen']:.4f}")
    print(f"  Span A        = {ichi['senkou_span_a']:.4f}")
    print(f"  Span B        = {ichi['senkou_span_b']:.4f}")
    print(f"  Cloud         = {'GREEN' if ichi['cloud_green'] else 'RED' if ichi['cloud_red'] else 'FLAT'}")
    print()
    print(f"  {_c('YLW')}--- Pattern / Structure ---{_c('RST')}")
    print(f"  Engulfing     = {sig.pattern or 'none'}")
    print(f"  Breakout      = {sig.breakout or 'none'}")
    print(f"  Divergence    = {sig.divergence or 'none'}")
    print(f"  Hist expand   = {sig.histogram_expanding}")
    print(f"  Spread noise  = {sig.spread_noise_val:.6f}")
    print()
    print(f"  {_c('YLW')}--- Scoring ---{_c('RST')}")
    print(f"  Direction     = {_c(sig.direction)}{sig.direction}{_c('RST')}")
    print(f"  Score         = {sig.score}/{sig.max_score} ({sig.confidence:.0%})")
    print(f"  Reasons:")
    for r in sig.reasons:
        print(f"    - {r}")
    print()


def _print_backtest(symbol: str, bt):
    print(f"\n{_c('CYAN')}--- Backtest: {symbol} ---{_c('RST')}")
    print(backtest_summary(bt))
    print()


# ---------------------------------------------------------------------------
# Main scan loop
# ---------------------------------------------------------------------------

def _scan(args):
    cfg = _load_config()
    scanner_cfg = cfg.get("scanner", {})
    quote = cfg.get("portfolio", {}).get("quote_asset", "USDT")
    fallback_symbols = _fallback_symbols(cfg)

    # Resolve symbols
    market = _effective_market(args.exchange, args.market)
    exchange = _connect_exchange(args.exchange, market)

    if args.symbols:
        symbols = [_normalize_symbol_input(s, quote) for s in args.symbols]
        symbols = [s for s in symbols if s and s not in _STABLE_BASES]
    elif args.top:
        print(f"Fetching top {args.top} symbols by volume on {args.exchange}...")
        try:
            symbols = _fetch_top_symbols(exchange, quote, args.top, market)
        except Exception as exc:
            log.warning("Failed to fetch top symbols: %s — using config fallback", exc)
            symbols = fallback_symbols
        print(f"Symbols: {', '.join(symbols)}\n")
    else:
        symbols = fallback_symbols

    interval = args.interval
    limit = args.limit

    results: list[tuple[str, SignalResult]] = []

    for sym in symbols:
        log.info("Scanning %s ...", sym)
        klines = _fetch_klines(exchange, sym, quote, interval, limit, market)
        if not klines:
            if args.verbose or args.debug:
                print(f"{_c('DIM')}{sym:>8}  -- no data --{_c('RST')}")
            continue

        sig = score_signal(klines, scanner_cfg)

        sl_tp = None
        if sig.direction != "HOLD":
            sl_tp = compute_sl_tp(klines, sig.direction, scanner_cfg)

        if args.debug:
            _print_debug(sym, klines, sig, scanner_cfg)
            if sl_tp:
                print(f"  SL = {sl_tp.stop_loss:.4f}  TP = {sl_tp.take_profit:.4f}  trail = {sl_tp.trailing_stop}  ({sl_tp.method})\n")

        if args.backtest:
            bt = run_backtest(klines, scanner_cfg)
            _print_backtest(sym, bt)

        results.append((sym, sig, sl_tp))

    # Summary table — always print unless debug already showed everything
    if not args.debug:
        print(f"\n{_c('BOLD')}{'Symbol':>8}  {'Dir':>4}  {'Score':>10}  {'Conf':>5}  {'RSI':>6}  {'MACD':>10}{_c('RST')}")
        print("-" * 55)
        for sym, sig, sl_tp in results:
            d = sig.direction
            print(
                f"{_c(d)}{sym:>8}  {d:>4}  "
                f"{sig.score:>2}/{sig.max_score:<2}       "
                f"{sig.confidence:>4.0%}  "
                f"{sig.rsi:>6.1f}  "
                f"{sig.macd_histogram:>10.6f}{_c('RST')}"
            )
            if args.verbose and sig.reasons:
                for r in sig.reasons:
                    print(f"           {_c('DIM')}{r}{_c('RST')}")
                if sl_tp and d != "HOLD":
                    print(
                        f"           SL={sl_tp.stop_loss:.4f}  "
                        f"TP={sl_tp.take_profit:.4f}  "
                        f"trail={sl_tp.trailing_stop}  "
                        f"({sl_tp.method})"
                    )
        print()

    # Print actionable signals
    actionable = [(s, sig, sl) for s, sig, sl in results if sig.direction != "HOLD"]
    if actionable:
        print(f"{_c('BOLD')}Actionable signals:{_c('RST')}")
        for sym, sig, sl_tp in actionable:
            _print_signal(sym, sig, sl_tp, verbose=True)
    else:
        print("No actionable signals.")

    if args.json:
        out = []
        for sym, sig, sl_tp in results:
            entry = {
                "symbol": sym,
                "direction": sig.direction,
                "score": sig.score,
                "max_score": sig.max_score,
                "confidence": sig.confidence,
                "rsi": sig.rsi,
                "macd_histogram": sig.macd_histogram,
                "atr": sig.atr_val,
                "reasons": sig.reasons,
            }
            if sl_tp:
                entry["sl"] = sl_tp.stop_loss
                entry["tp"] = sl_tp.take_profit
                entry["trailing"] = sl_tp.trailing_stop
            out.append(entry)
        print(json.dumps(out, indent=2))

    return results


# ---------------------------------------------------------------------------
# Watch mode — continuous monitoring with alerts
# ---------------------------------------------------------------------------

def _beep():
    """Terminal bell/beep to get attention."""
    sys.stdout.write("\a")
    sys.stdout.flush()


def _watch(args):
    """Re-scan on a timer, alert when signal direction changes."""
    cfg = _load_config()
    scanner_cfg = cfg.get("scanner", {})
    quote = cfg.get("portfolio", {}).get("quote_asset", "USDT")
    fallback_symbols = _fallback_symbols(cfg)

    market = _effective_market(args.exchange, args.market)
    exchange = _connect_exchange(args.exchange, market)

    if args.symbols:
        symbols = [_normalize_symbol_input(s, quote) for s in args.symbols]
        symbols = [s for s in symbols if s and s not in _STABLE_BASES]
    else:
        symbols = fallback_symbols

    # Track previous direction per symbol
    prev_direction: dict[str, str] = {}
    prev_reasons: dict[str, set[str]] = {}
    prev_score: dict[str, int] = {}
    # Track entry prices if given
    entry_prices: dict[str, float] = {}
    if args.entry:
        for pair in args.entry:
            sym, price = pair.split("=")
            entry_prices[sym.upper()] = float(price)

    interval_sec = args.watch
    print(f"{_c('BOLD')}Watch mode: scanning {', '.join(symbols)} every {interval_sec}s{_c('RST')}")
    if entry_prices:
        for sym, price in entry_prices.items():
            print(f"  Tracking position: {sym} entry @ {price}")
    print(f"  Press Ctrl+C to stop.\n")

    try:
        while True:
            now = datetime.now().strftime("%H:%M:%S")
            print(f"{_c('DIM')}[{now}]{_c('RST')} Scanning...", end="", flush=True)

            for sym in symbols:
                klines = _fetch_klines(exchange, sym, quote, args.interval, args.limit, market)
                if not klines:
                    continue

                sig = score_signal(klines, scanner_cfg)
                price = float(klines[-1][4])
                d = sig.direction
                prev = prev_direction.get(sym)
                old_reasons = prev_reasons.get(sym)
                old_score = prev_score.get(sym, sig.score)

                # Detect signal change
                changed = prev is not None and prev != d
                if changed:
                    _beep()
                    print(
                        f"\n{_c('BOLD')}** SIGNAL CHANGE ** {sym}: "
                        f"{_c(prev)}{prev}{_c('RST')} -> {_c(d)}{d}{_c('RST')} "
                        f"(score {sig.score}/{sig.max_score}, RSI {sig.rsi:.1f})"
                    )
                    for r in sig.reasons:
                        print(f"   {_c('DIM')}{r}{_c('RST')}")

                # Detect dropped filters (reason lines lost as score weakens)
                current_reasons = set(sig.reasons)
                if old_reasons is not None:
                    dropped = sorted(old_reasons - current_reasons)
                    if dropped and sig.score < old_score:
                        print(
                            f"\n{_c('YLW')}-- FILTERS DROPPED {sym}: "
                            f"{old_score}->{sig.score}{_c('RST')}"
                        )
                        for r in dropped:
                            print(f"   {_c('DIM')}- {r}{_c('RST')}")

                prev_direction[sym] = d
                prev_reasons[sym] = current_reasons
                prev_score[sym] = sig.score

                # Position tracking
                if sym in entry_prices:
                    entry_p = entry_prices[sym]
                    pnl = price - entry_p
                    pnl_pct = (pnl / entry_p) * 100
                    sl_tp = compute_sl_tp(klines, "BUY", scanner_cfg)
                    color = _c("BUY") if pnl >= 0 else _c("SELL")

                    sl_hit = price <= sl_tp.stop_loss
                    tp_hit = price >= sl_tp.take_profit
                    trail_hit = sl_tp.trailing_stop and price <= sl_tp.trailing_stop

                    status = ""
                    if sl_hit:
                        _beep()
                        status = f" {_c('SELL')}** STOP LOSS HIT **{_c('RST')}"
                    elif trail_hit:
                        _beep()
                        status = f" {_c('SELL')}** TRAILING STOP HIT **{_c('RST')}"
                    elif tp_hit:
                        _beep()
                        status = f" {_c('BUY')}** TAKE PROFIT HIT **{_c('RST')}"

                    print(
                        f"\n  {_c('BOLD')}{sym}{_c('RST')}  "
                        f"price={price:.4f}  "
                        f"entry={entry_p:.4f}  "
                        f"{color}PnL={pnl:+.4f} ({pnl_pct:+.2f}%){_c('RST')}  "
                        f"signal={_c(d)}{d}{_c('RST')} {sig.score}/{sig.max_score}  "
                        f"SL={sl_tp.stop_loss:.4f}  TP={sl_tp.take_profit:.4f}"
                        f"{status}"
                    )
                else:
                    # No position, just show signal status
                    print(
                        f"\n  {sym}  price={price:.4f}  "
                        f"{_c(d)}{d}{_c('RST')} {sig.score}/{sig.max_score}  "
                        f"RSI={sig.rsi:.1f}"
                    )

            print()  # blank line between cycles
            time.sleep(interval_sec)

    except KeyboardInterrupt:
        print(f"\n{_c('BOLD')}Watch stopped.{_c('RST')}")


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="unified_scanner",
        description="Unified Signal Scanner — scan any symbols with all indicators",
    )
    p.add_argument(
        "symbols", nargs="*", default=None,
        help="Symbols to scan (e.g. BTC ETH SOL). Omit to use [scanner].symbols or [portfolio].coins.",
    )
    p.add_argument(
        "--top", type=int, default=None, metavar="N",
        help="Scan top N symbols by 24h volume instead of specifying symbols.",
    )
    p.add_argument(
        "--exchange", default="binance",
        help="Exchange to use via ccxt (default: binance).",
    )
    p.add_argument(
        "--market", choices=["auto", "spot", "futures"], default="auto",
        help="Market type to scan (default: auto; bitget=>futures, others=>spot).",
    )
    p.add_argument(
        "--interval", "-i", default="15m",
        help="Candle interval/timeframe (default: 15m).",
    )
    p.add_argument(
        "--limit", "-l", type=int, default=120,
        help="Number of candles to fetch (default: 120).",
    )
    p.add_argument(
        "--debug", "-d", action="store_true",
        help="Full debug dump with all indicator values for each symbol.",
    )
    p.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show reasons and SL/TP for each signal.",
    )
    p.add_argument(
        "--backtest", action="store_true",
        help="Run backtest on fetched klines for each symbol.",
    )
    p.add_argument(
        "--json", action="store_true",
        help="Output results as JSON (for piping to other tools).",
    )
    p.add_argument(
        "--watch", type=int, default=None, metavar="SECS",
        help="Watch mode: re-scan every SECS seconds and alert on signal changes.",
    )
    p.add_argument(
        "--entry", nargs="+", metavar="SYM=PRICE",
        help="Track open positions (e.g. --entry SOL=87.70). Shows PnL and SL/TP alerts.",
    )
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Set up logging — scope debug to our logger only; keep ccxt quiet
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.WARNING,
    )
    scanner_level = logging.DEBUG if args.debug else (logging.INFO if args.verbose else logging.WARNING)
    logging.getLogger("unified_scanner").setLevel(scanner_level)

    if args.watch:
        _watch(args)
    else:
        _scan(args)


if __name__ == "__main__":
    main()
