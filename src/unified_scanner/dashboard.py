#!/usr/bin/env python3
"""
Unified Scanner — Live Web Dashboard.

Runs 24/7, scans top symbols every 5 minutes, serves a live dashboard.
Auto-fetches open positions from Bitget and sends Telegram alerts.

Usage:
  python -m src.unified_scanner.dashboard
  python -m src.unified_scanner.dashboard --port 8080 --top 30
  python -m src.unified_scanner.dashboard --exchange bitget
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string

# Ensure project root on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_DIR = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Load credentials from project root .env; then optional local override file.
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv(_PACKAGE_DIR / ".env")

from .signal_scorer import score_signal, SignalResult
from .sl_tp import compute_sl_tp
from .indicators import (
    rsi, macd, atr, bollinger_bands, stochastic, ichimoku,
    laguerre_rsi, hma, keltner_channel, rolling_vwap,
)

log = logging.getLogger("scanner_dashboard")
_STABLE_BASES = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "FDUSD", "USDE", "USD1", "PYUSD"
}

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

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


def _fallback_symbols(cfg: dict) -> list[str]:
    scanner_symbols = cfg.get("scanner", {}).get("symbols", [])
    if scanner_symbols:
        return [str(s).upper() for s in scanner_symbols if str(s).upper() not in _STABLE_BASES]
    return [str(s).upper() for s in cfg.get("portfolio", {}).get("coins", ["BTC", "ETH", "SOL", "BNB"]) if str(s).upper() not in _STABLE_BASES]


# ---------------------------------------------------------------------------
# Exchange helpers
# ---------------------------------------------------------------------------

_exchange_lock = threading.Lock()
_exchange_public = None     # public (no auth) for market data
_exchange_public_key = None
_exchange_private = None    # authenticated for positions


def _effective_market(exchange_id: str) -> str:
    return "futures" if str(exchange_id).lower() == "bitget" else "spot"


def _get_exchange(exchange_id: str = "binance", market: str = "spot"):
    """Public exchange instance for market data (no auth needed)."""
    global _exchange_public, _exchange_public_key
    with _exchange_lock:
        exchange_key = (str(exchange_id).lower(), market)
        if _exchange_public is None or _exchange_public_key != exchange_key:
            import ccxt
            cls = getattr(ccxt, exchange_id, None)
            if cls is None:
                raise ValueError(f"Exchange {exchange_id!r} not in ccxt")
            opts = {"enableRateLimit": True}
            if market == "futures":
                default_type = "swap" if str(exchange_id).lower() in {"bitget", "bybit", "okx"} else "future"
                opts["options"] = {"defaultType": default_type}
            _exchange_public = cls(opts)
            _exchange_public.load_markets()
            _exchange_public_key = exchange_key
    return _exchange_public


def _get_private_exchange():
    """Authenticated Bitget exchange for fetching positions/balances."""
    global _exchange_private
    with _exchange_lock:
        if _exchange_private is None:
            api_key = os.getenv("BITGET_API_KEY", "")
            api_secret = os.getenv("BITGET_API_SECRET", "")
            passphrase = os.getenv("BITGET_API_PASSPHRASE", "")
            if not api_key or not api_secret:
                log.warning("No Bitget API credentials — position auto-fetch disabled")
                return None
            import ccxt
            _exchange_private = ccxt.bitget({
                "apiKey": api_key,
                "secret": api_secret,
                "password": passphrase,
                "enableRateLimit": True,
            })
            _exchange_private.load_markets()
    return _exchange_private


def _fetch_open_positions(quote: str) -> dict[str, float]:
    """Fetch real open spot positions from Bitget. Returns {SYMBOL: avg_entry_price}."""
    exchange = _get_private_exchange()
    if exchange is None:
        return {}
    try:
        balance = exchange.fetch_balance()
        positions = {}
        for coin, bal in balance.get("total", {}).items():
            if coin.upper() == quote.upper():
                continue  # skip quote asset itself
            amount = float(bal) if bal else 0
            if amount <= 0:
                continue
            # Get current price to see if it's a meaningful holding
            pair = f"{coin}/{quote}"
            if pair not in exchange.markets:
                continue
            ticker = exchange.fetch_ticker(pair)
            current_price = ticker.get("last", 0)
            usd_value = amount * current_price if current_price else 0
            if usd_value < 1.0:  # skip dust (< $1)
                continue
            # Try to get average entry from recent trades
            entry_price = _get_avg_entry(exchange, pair, amount)
            if entry_price:
                positions[coin.upper()] = entry_price
            else:
                # Fallback: use current price (no entry info available)
                positions[coin.upper()] = current_price
            log.info("Position found: %s  qty=%.6f  entry=%.4f  value=$%.2f",
                     coin, amount, positions[coin.upper()], usd_value)
        return positions
    except Exception as exc:
        log.warning("Failed to fetch positions: %s", exc)
        return {}


def _get_avg_entry(exchange, pair: str, qty: float) -> float | None:
    """Try to compute average entry price from recent trades."""
    try:
        trades = exchange.fetch_my_trades(pair, limit=50)
        if not trades:
            return None
        # Walk backwards through buy trades to aggregate entry
        remaining = qty
        total_cost = 0.0
        for t in reversed(trades):
            if t["side"] != "buy":
                continue
            fill_qty = float(t["amount"])
            fill_price = float(t["price"])
            take = min(fill_qty, remaining)
            total_cost += take * fill_price
            remaining -= take
            if remaining <= 0:
                break
        filled = qty - max(remaining, 0)
        if filled > 0:
            return total_cost / filled
    except Exception as exc:
        log.debug("Could not fetch trades for %s: %s", pair, exc)
    return None


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _fetch_open_futures_positions() -> list[dict]:
    """Fetch open futures positions from Bitget via ccxt; returns normalized rows."""
    exchange = _get_private_exchange()
    if exchange is None:
        return []
    try:
        positions = exchange.fetch_positions()
    except Exception as exc:
        log.warning("Failed to fetch futures positions: %s", exc)
        return []

    rows: list[dict] = []
    for p in positions or []:
        contracts = _safe_float(p.get("contracts"), 0.0)
        if contracts <= 0:
            info = p.get("info") or {}
            contracts = abs(_safe_float(info.get("positionAmt"), 0.0))
        if contracts <= 0:
            continue

        info = p.get("info") or {}
        side = str(p.get("side") or "").upper()
        if not side:
            amt = _safe_float(info.get("positionAmt"), 0.0)
            side = "LONG" if amt > 0 else "SHORT" if amt < 0 else "UNKNOWN"

        rows.append(
            {
                "symbol": str(p.get("symbol") or info.get("symbol") or ""),
                "side": side,
                "contracts": round(contracts, 6),
                "entry": round(_safe_float(p.get("entryPrice"), _safe_float(info.get("entryPrice"), 0.0)), 6),
                "mark": round(_safe_float(p.get("markPrice"), _safe_float(info.get("markPrice"), 0.0)), 6),
                "notional": round(abs(_safe_float(p.get("notional"), _safe_float(info.get("notional"), 0.0))), 4),
                "unrealized_pnl": round(_safe_float(p.get("unrealizedPnl"), _safe_float(info.get("unrealizedPL"), 0.0)), 4),
                "pnl_pct": round(_safe_float(p.get("percentage"), 0.0), 2),
            }
        )
    rows.sort(key=lambda x: abs(x.get("notional", 0.0)), reverse=True)
    return rows


def _load_futures_activities(limit: int = 50) -> list[dict]:
    path = _PROJECT_ROOT / "state" / "futures_state.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        acts = data.get("activities", []) if isinstance(data, dict) else []
        if not isinstance(acts, list):
            return []
        return acts[-limit:]
    except Exception:
        return []


def _extract_pnl_percent(message: str) -> float | None:
    if not message or "pnl=" not in message:
        return None
    try:
        tail = message.split("pnl=", 1)[1]
        token = tail.split("%", 1)[0].strip()
        return float(token)
    except Exception:
        return None


def _compute_performance(activities: list[dict]) -> dict:
    closed = 0
    wins = 0
    losses = 0
    net_pnl_pct = 0.0
    pnl_samples = 0
    for a in activities:
        if str(a.get("market", "")).lower() != "futures":
            continue
        action = str(a.get("action", ""))
        if not action.startswith("CLOSE_"):
            continue
        closed += 1
        pnl_pct = _extract_pnl_percent(str(a.get("message", "")))
        if pnl_pct is None:
            continue
        pnl_samples += 1
        net_pnl_pct += pnl_pct
        if pnl_pct > 0:
            wins += 1
        elif pnl_pct < 0:
            losses += 1
    win_rate = (wins / pnl_samples * 100.0) if pnl_samples else 0.0
    avg_pnl_pct = (net_pnl_pct / pnl_samples) if pnl_samples else 0.0
    return {
        "closed_trades": closed,
        "wins": wins,
        "losses": losses,
        "pnl_samples": pnl_samples,
        "win_rate_pct": round(win_rate, 2),
        "net_pnl_pct": round(net_pnl_pct, 2),
        "avg_pnl_pct": round(avg_pnl_pct, 2),
    }


def _load_spot_performance(price_map: dict[str, float] | None = None) -> dict:
    path = _PROJECT_ROOT / "state" / "state.json"
    if not path.exists():
        return {"buy_count": 0, "sell_count": 0, "closed_trades": 0, "full_closed_trades": 0, "realized_pnl_usdt": 0.0, "fees_usdt": 0.0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pnl = data.get("pnl", {}) if isinstance(data, dict) else {}
        metrics = data.get("metrics", {}) if isinstance(data, dict) else {}
        positions = data.get("positions", {}) if isinstance(data, dict) else {}
        acts = data.get("activities", []) if isinstance(data, dict) else []
        meta = data.get("meta", {}) if isinstance(data, dict) else {}
        full_close_count = int(float(meta.get("spot_full_close_count", 0.0) or 0.0))
        buy_from_acts = 0
        sell_from_acts = 0
        if isinstance(acts, list):
            for a in acts:
                action = str((a or {}).get("action", "")).upper()
                if action.startswith("SPOT_BUY"):
                    buy_from_acts += 1
                elif action in {"SPOT_SELL", "SPOT_SELL_CONVERT"}:
                    sell_from_acts += 1
        buy_count = int(float(metrics.get("execution.trade.buy.count", 0.0) or 0.0)) or buy_from_acts
        sell_count = int(float(metrics.get("execution.trade.sell.count", 0.0) or 0.0)) or sell_from_acts
        unrealized = 0.0
        pm = price_map or {}
        if isinstance(positions, dict):
            for sym, pos in positions.items():
                if not isinstance(pos, dict):
                    continue
                amt = float(pos.get("amount", 0.0) or 0.0)
                avg = float(pos.get("avg_price", 0.0) or 0.0)
                px = float(pm.get(str(sym).upper(), 0.0) or 0.0)
                if amt > 0 and avg > 0 and px > 0:
                    unrealized += (px - avg) * amt
        return {
            "buy_count": buy_count,
            "sell_count": sell_count,
            "closed_trades": sell_count,
            "full_closed_trades": full_close_count,
            "realized_pnl_usdt": round(float(pnl.get("realized_profit_usdt", 0.0) or 0.0), 4),
            "unrealized_pnl_usdt": round(unrealized, 4),
            "fees_usdt": round(float(pnl.get("fees_usdt", 0.0) or 0.0), 4),
        }
    except Exception:
        return {"buy_count": 0, "sell_count": 0, "closed_trades": 0, "full_closed_trades": 0, "realized_pnl_usdt": 0.0, "unrealized_pnl_usdt": 0.0, "fees_usdt": 0.0}


def _load_spot_activities(limit: int = 80) -> list[dict]:
    path = _PROJECT_ROOT / "state" / "state.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        acts = data.get("activities", []) if isinstance(data, dict) else []
        if not isinstance(acts, list):
            return []
        return acts[-limit:]
    except Exception:
        return []


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


def _fetch_klines(exchange, symbol: str, quote: str, interval: str, limit: int, market: str) -> list:
    pair = _resolve_pair(exchange, symbol, quote, market)
    if not pair:
        return []
    return exchange.fetch_ohlcv(pair, timeframe=interval, limit=limit)


def _fetch_top_symbols(exchange, quote: str, top_n: int, fallback: list[str], market: str) -> list[str]:
    """Top N by 24h volume; falls back to config coins on error."""
    try:
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
        if symbols:
            return symbols
    except Exception as exc:
        log.warning("Failed to fetch top symbols: %s — using config fallback", exc)
    return fallback


# ---------------------------------------------------------------------------
# Shared scan state
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Telegram alerts
# ---------------------------------------------------------------------------

def _send_telegram(message: str):
    """Send a message via Telegram bot."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        log.warning("Telegram send failed: %s", exc)


# ---------------------------------------------------------------------------
# Shared scan state
# ---------------------------------------------------------------------------

class ScanState:
    """Thread-safe container for latest scan results."""

    def __init__(self):
        self.results: list[dict] = []
        self.last_scan: str = "never"
        self.next_scan: str = ""
        self.cycle_count: int = 0
        self.symbols_count: int = 0
        self.entry_prices: dict[str, float] = {}  # auto-fetched + manual
        self.futures_positions: list[dict] = []
        self.prev_directions: dict[str, str] = {}  # for change detection
        self.prev_reasons: dict[str, set[str]] = {}
        self.prev_scores: dict[str, int] = {}
        self.activities: list[dict] = []
        self.performance: dict = {}
        self._lock = threading.Lock()

    def add_activity(self, action: str, symbol: str, message: str, market: str = "spot"):
        with self._lock:
            self.activities.append(
                {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "market": market,
                    "action": action,
                    "symbol": symbol,
                    "message": message,
                }
            )
            if len(self.activities) > 200:
                self.activities = self.activities[-200:]

    def update(
        self,
        results: list[dict],
        ts: str,
        next_ts: str,
        futures_positions: list[dict],
        fused_activities: list[dict],
        performance: dict,
    ):
        with self._lock:
            self.results = results
            self.last_scan = ts
            self.next_scan = next_ts
            self.cycle_count += 1
            self.symbols_count = len(results)
            self.futures_positions = futures_positions
            self.activities = fused_activities[-200:]
            self.performance = performance

    def get(self) -> dict:
        with self._lock:
            return {
                "results": list(self.results),
                "last_scan": self.last_scan,
                "next_scan": self.next_scan,
                "cycle": self.cycle_count,
                "symbols_count": self.symbols_count,
                "futures_positions": list(self.futures_positions),
                "activities": list(self.activities),
                "performance": dict(self.performance),
            }


state = ScanState()


# ---------------------------------------------------------------------------
# Background scanner thread
# ---------------------------------------------------------------------------

def _scan_cycle(exchange_id: str, top_n: int, interval: str, limit: int, sleep_min: int):
    """Runs forever: scan, sleep, repeat."""
    cfg = _load_config()
    scanner_cfg = cfg.get("scanner", {})
    telegram_min_score = int(scanner_cfg.get("telegram_min_score", scanner_cfg.get("min_score_for_signal", 4)))
    dashboard_filter_dropped_activity = bool(cfg.get("alerts", {}).get("dashboard_filter_dropped_activity", False))
    quote = cfg.get("portfolio", {}).get("quote_asset", "USDT")
    fallback_coins = _fallback_symbols(cfg)
    market = _effective_market(exchange_id)

    exchange = _get_exchange(exchange_id, market)

    # Send startup message
    _send_telegram("\U0001f680 <b>Scanner Dashboard started</b>\n"
                   f"Scanning top {top_n} symbols every {sleep_min} min")

    while True:
        try:
            now = datetime.now()
            log.info("Scan cycle #%d starting at %s", state.cycle_count + 1, now.strftime("%H:%M:%S"))

            # Auto-fetch open positions from Bitget
            try:
                live_positions = _fetch_open_positions(quote)
                if live_positions:
                    state.entry_prices.update(live_positions)
                    log.info("Auto-fetched %d open positions", len(live_positions))
            except Exception as exc:
                log.warning("Position fetch failed: %s", exc)
            futures_positions = _fetch_open_futures_positions()

            symbols = _fetch_top_symbols(exchange, quote, top_n, fallback_coins, market)

            # Also include symbols we have positions in
            for pos_sym in state.entry_prices:
                if pos_sym.upper() in _STABLE_BASES:
                    continue
                if pos_sym.upper() not in [s.upper() for s in symbols]:
                    symbols.append(pos_sym.upper())

            # Always include fallback coins even if not in top N
            for fb in fallback_coins:
                if fb.upper() not in [s.upper() for s in symbols]:
                    symbols.append(fb.upper())

            results = []
            for sym in symbols:
                try:
                    klines = _fetch_klines(exchange, sym, quote, interval, limit, market)
                    if not klines:
                        continue

                    sig = score_signal(klines, scanner_cfg)
                    price = float(klines[-1][4])

                    row = {
                        "symbol": sym,
                        "price": price,
                        "direction": sig.direction,
                        "score": sig.score,
                        "max_score": sig.max_score,
                        "confidence": sig.confidence,
                        "rsi": round(sig.rsi, 1),
                        "macd_hist": round(sig.macd_histogram, 6),
                        "atr": round(sig.atr_val, 6),
                        "reasons": sig.reasons,
                    }

                    # SL/TP for non-HOLD
                    if sig.direction != "HOLD":
                        sl_tp = compute_sl_tp(klines, sig.direction, scanner_cfg)
                        row["sl"] = round(sl_tp.stop_loss, 4)
                        row["tp"] = round(sl_tp.take_profit, 4)
                        row["trailing"] = round(sl_tp.trailing_stop, 4) if sl_tp.trailing_stop else None
                    else:
                        row["sl"] = None
                        row["tp"] = None
                        row["trailing"] = None

                    # Position tracking
                    if sym.upper() in state.entry_prices:
                        entry_p = state.entry_prices[sym.upper()]
                        pnl = price - entry_p
                        pnl_pct = (pnl / entry_p) * 100
                        row["entry"] = entry_p
                        row["pnl"] = round(pnl, 4)
                        row["pnl_pct"] = round(pnl_pct, 2)
                    else:
                        row["entry"] = None
                        row["pnl"] = None
                        row["pnl_pct"] = None

                    # Extra indicators for detail panel
                    closes = [float(k[4]) for k in klines]
                    highs = [float(k[2]) for k in klines]
                    lows = [float(k[3]) for k in klines]
                    volumes = [float(k[5]) for k in klines]

                    m = macd(closes)
                    bb = bollinger_bands(closes)
                    stoch = stochastic(highs, lows, closes)

                    row["macd_line"] = round(m["macd_line"], 6)
                    row["macd_signal"] = round(m["signal"], 6)
                    row["bb_upper"] = round(bb["upper"], 4)
                    row["bb_mid"] = round(bb["mid"], 4)
                    row["bb_lower"] = round(bb["lower"], 4)
                    row["stoch_k"] = round(stoch["k"], 1)
                    row["stoch_d"] = round(stoch["d"], 1)

                    results.append(row)

                except Exception as exc:
                    log.warning("Error scanning %s: %s", sym, exc)
                    continue

            # Sort: actionable first (BUY/SELL), then by score desc
            results.sort(key=lambda r: (0 if r["direction"] != "HOLD" else 1, -r["score"]))

            # --- Telegram alerts ---
            for row in results:
                sym = row["symbol"]
                d = row["direction"]
                prev = state.prev_directions.get(sym)
                prev_reasons = state.prev_reasons.get(sym)
                prev_score = state.prev_scores.get(sym, row["score"])
                current_reasons = set(row.get("reasons") or [])

                # Signal direction changed
                if prev is not None and prev != d:
                    if row["score"] < telegram_min_score:
                        state.prev_directions[sym] = d
                        continue
                    emoji = "\U0001f7e2" if d == "BUY" else "\U0001f534" if d == "SELL" else "\u26aa"
                    msg = (f"{emoji} <b>Signal change: {sym}</b>\n"
                           f"{prev} \u2192 {d}  (score {row['score']}/{row['max_score']})\n"
                           f"Price: {row['price']}  RSI: {row['rsi']}")
                    if row.get("sl"):
                        msg += f"\nSL: {row['sl']}  TP: {row['tp']}"
                    _send_telegram(msg)
                    state.add_activity("SIGNAL_CHANGE", sym, f"{prev} -> {d} score={row['score']}/{row['max_score']}")

                # Track which filters were dropped when score weakens
                if prev_reasons is not None:
                    dropped = sorted(prev_reasons - current_reasons)
                    if dropped and row["score"] < prev_score:
                        if dashboard_filter_dropped_activity:
                            state.add_activity(
                                "FILTER_DROPPED",
                                sym,
                                f"score {prev_score}->{row['score']}; dropped: {', '.join(dropped[:3])}",
                            )

                state.prev_directions[sym] = d
                state.prev_reasons[sym] = current_reasons
                state.prev_scores[sym] = int(row["score"])

                # Position alerts: SL/TP hit
                if row.get("entry") is not None and row.get("sl") is not None:
                    price = row["price"]
                    if price <= row["sl"]:
                        _send_telegram(
                            f"\U0001f6a8 <b>STOP LOSS HIT: {sym}</b>\n"
                            f"Price {price} \u2264 SL {row['sl']}\n"
                            f"Entry was {row['entry']}  PnL: {row['pnl_pct']}%"
                        )
                        state.add_activity("STOP_LOSS_HIT", sym, f"price={price} sl={row['sl']} pnl={row['pnl_pct']}%")
                    elif row.get("trailing") and price <= row["trailing"]:
                        _send_telegram(
                            f"\U0001f6a8 <b>TRAILING STOP HIT: {sym}</b>\n"
                            f"Price {price} \u2264 Trail {row['trailing']}\n"
                            f"Entry was {row['entry']}  PnL: {row['pnl_pct']}%"
                        )
                        state.add_activity("TRAILING_STOP_HIT", sym, f"price={price} trail={row['trailing']} pnl={row['pnl_pct']}%")
                    elif price >= row["tp"]:
                        _send_telegram(
                            f"\U0001f389 <b>TAKE PROFIT HIT: {sym}</b>\n"
                            f"Price {price} \u2265 TP {row['tp']}\n"
                            f"Entry was {row['entry']}  PnL: {row['pnl_pct']}%"
                        )
                        state.add_activity("TAKE_PROFIT_HIT", sym, f"price={price} tp={row['tp']} pnl={row['pnl_pct']}%")

            next_ts = (now + timedelta(minutes=sleep_min)).strftime("%H:%M:%S")
            futures_acts = _load_futures_activities(limit=60)
            local_acts = state.get().get("activities", [])
            spot_acts = _load_spot_activities(limit=80)
            all_activities = sorted(local_acts + spot_acts + futures_acts, key=lambda a: str(a.get("ts", "")), reverse=True)[:120]
            performance = {
                "futures": _compute_performance(all_activities),
                "spot": _load_spot_performance({str(r.get("symbol", "")).upper(): float(r.get("price", 0.0) or 0.0) for r in results}),
            }
            state.update(
                results,
                now.strftime("%Y-%m-%d %H:%M:%S"),
                next_ts,
                futures_positions=futures_positions,
                fused_activities=all_activities,
                performance=performance,
            )
            log.info("Scan complete: %d symbols, sleeping %d min", len(results), sleep_min)

        except Exception as exc:
            log.error("Scan cycle error: %s", exc, exc_info=True)

        time.sleep(sleep_min * 60)


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)


@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route("/api/scan")
def api_scan():
    return jsonify(state.get())


@app.route("/api/positions")
def api_positions():
    return jsonify(state.entry_prices)


# ---------------------------------------------------------------------------
# HTML Dashboard (embedded)
# ---------------------------------------------------------------------------

DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Unified Scanner Dashboard</title>
<style>
  :root {
    --bg: #0d1117; --bg2: #161b22; --bg3: #21262d;
    --text: #c9d1d9; --text2: #8b949e; --border: #30363d;
    --green: #3fb950; --red: #f85149; --yellow: #d29922;
    --blue: #58a6ff; --cyan: #39d2c0;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; }

  .header {
    background: var(--bg2); border-bottom: 1px solid var(--border);
    padding: 16px 24px; display: flex; justify-content: space-between; align-items: center;
  }
  .header h1 { font-size: 20px; color: var(--cyan); }
  .header .meta { font-size: 13px; color: var(--text2); text-align: right; }
  .header .meta span { margin-left: 16px; }
  .live-dot { display: inline-block; width: 8px; height: 8px; background: var(--green);
    border-radius: 50%; margin-right: 6px; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }

  .stats {
    display: flex; gap: 16px; padding: 16px 24px; flex-wrap: wrap;
  }
  .stat-card {
    background: var(--bg2); border: 1px solid var(--border); border-radius: 8px;
    padding: 12px 20px; min-width: 140px; flex: 1;
  }
  .stat-card .label { font-size: 11px; color: var(--text2); text-transform: uppercase; letter-spacing: 1px; }
  .stat-card .value { font-size: 24px; font-weight: 600; margin-top: 4px; }

  .positions {
    padding: 0 24px; margin-bottom: 8px;
  }
  .position-bar {
    background: var(--bg2); border: 1px solid var(--border); border-radius: 8px;
    padding: 12px 20px; display: flex; gap: 24px; align-items: center; flex-wrap: wrap;
  }
  .position-bar .pos-sym { font-weight: 700; font-size: 16px; }
  .position-bar .pos-detail { font-size: 13px; color: var(--text2); }
  .position-bar .pos-pnl { font-size: 18px; font-weight: 600; }

  .table-wrap { padding: 16px 24px; overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th { background: var(--bg2); color: var(--text2); font-size: 11px; text-transform: uppercase;
    letter-spacing: 1px; padding: 10px 12px; text-align: left; border-bottom: 2px solid var(--border);
    position: sticky; top: 0; }
  td { padding: 10px 12px; border-bottom: 1px solid var(--border); }
  tr:hover { background: var(--bg3); }
  tr.buy-row { border-left: 3px solid var(--green); }
  tr.sell-row { border-left: 3px solid var(--red); }
  tr.hold-row { border-left: 3px solid var(--border); }

  .dir-badge {
    display: inline-block; padding: 2px 10px; border-radius: 4px;
    font-weight: 700; font-size: 12px; text-transform: uppercase;
  }
  .dir-BUY { background: rgba(63,185,80,0.15); color: var(--green); }
  .dir-SELL { background: rgba(248,81,73,0.15); color: var(--red); }
  .dir-HOLD { background: rgba(139,148,158,0.1); color: var(--text2); }

  .score-bar { display: inline-flex; gap: 2px; align-items: center; }
  .score-pip { width: 8px; height: 16px; border-radius: 2px; }
  .pip-on { background: var(--cyan); }
  .pip-off { background: var(--bg3); }

  .reason-list { font-size: 12px; color: var(--text2); max-width: 320px; }
  .reason-list li { margin-bottom: 2px; }

  .pnl-pos { color: var(--green); }
  .pnl-neg { color: var(--red); }

  .countdown { font-variant-numeric: tabular-nums; }

  .detail-row { display: none; }
  .detail-row.open { display: table-row; }
  .detail-cell { padding: 12px 24px; background: var(--bg2); }
  .detail-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
  .detail-item { font-size: 13px; }
  .detail-item .dlabel { color: var(--text2); font-size: 11px; }

  .clickable { cursor: pointer; }

  .footer { text-align: center; padding: 16px; font-size: 12px; color: var(--text2); }

  @media (max-width: 768px) {
    .stats { flex-direction: column; }
    .header { flex-direction: column; gap: 8px; }
  }
</style>
</head>
<body>

<div class="header">
  <h1><span class="live-dot"></span> Unified Signal Scanner</h1>
  <div class="meta">
    <span>Last scan: <strong id="lastScan">--</strong></span>
    <span>Next in: <strong id="countdown" class="countdown">--</strong></span>
    <span>Cycle: <strong id="cycle">0</strong></span>
  </div>
</div>

<div class="stats">
  <div class="stat-card">
    <div class="label">Symbols</div>
    <div class="value" id="symCount">--</div>
  </div>
  <div class="stat-card">
    <div class="label">Buy Signals</div>
    <div class="value" id="buyCount" style="color:var(--green)">--</div>
  </div>
  <div class="stat-card">
    <div class="label">Sell Signals</div>
    <div class="value" id="sellCount" style="color:var(--red)">--</div>
  </div>
  <div class="stat-card">
    <div class="label">Avg Confidence</div>
    <div class="value" id="avgConf">--</div>
  </div>
  <div class="stat-card">
    <div class="label">Closed Trades</div>
    <div class="value" id="closedTrades">--</div>
  </div>
  <div class="stat-card">
    <div class="label">Spot Buys</div>
    <div class="value" id="spotBuys">--</div>
  </div>
  <div class="stat-card">
    <div class="label">Spot Sells</div>
    <div class="value" id="spotSells">--</div>
  </div>
  <div class="stat-card">
    <div class="label">Spot Full Closes</div>
    <div class="value" id="spotFullCloses">--</div>
  </div>
  <div class="stat-card">
    <div class="label">Spot Realized PnL</div>
    <div class="value" id="spotRealizedPnl">--</div>
  </div>
  <div class="stat-card">
    <div class="label">Spot Unrealized PnL</div>
    <div class="value" id="spotUnrealizedPnl">--</div>
  </div>
  <div class="stat-card">
    <div class="label">Win Rate</div>
    <div class="value" id="winRate">--</div>
  </div>
  <div class="stat-card">
    <div class="label">Net Realized PnL %</div>
    <div class="value" id="netPnlPct">--</div>
  </div>
  <div class="stat-card">
    <div class="label">Avg PnL %</div>
    <div class="value" id="avgPnlPct">--</div>
  </div>
</div>

<div class="positions" id="spotPositionsWrap"></div>
<div class="positions" id="futuresPositionsWrap"></div>
<div class="positions" id="activitiesWrap"></div>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>Symbol</th>
        <th>Price</th>
        <th>Signal</th>
        <th>Score</th>
        <th>Confidence</th>
        <th>RSI</th>
        <th>MACD Hist</th>
        <th>Stoch %K/%D</th>
        <th>SL / TP</th>
        <th>Reasons</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
</div>

<div class="footer">
  Scanner runs 24/7 &mdash; refresh every 15s &mdash; scan cycle every 5 min
</div>

<script>
let nextScanTime = null;

function formatPrice(p) {
  if (p === null || p === undefined) return '--';
  if (p >= 1000) return p.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
  if (p >= 1) return p.toFixed(4);
  return p.toFixed(6);
}

function scorePips(score, max) {
  let html = '<div class="score-bar">';
  for (let i = 0; i < max; i++) {
    html += `<div class="score-pip ${i < score ? 'pip-on' : 'pip-off'}"></div>`;
  }
  html += ` <span style="margin-left:4px;font-size:12px">${score}/${max}</span></div>`;
  return html;
}

function renderSpotPositions(results) {
  const wrap = document.getElementById('spotPositionsWrap');
  const positions = results.filter(r => r.entry !== null);
  if (!positions.length) { wrap.innerHTML = ''; return; }

  let html = '<div style="margin-bottom:8px;color:var(--text2);font-size:12px;text-transform:uppercase;letter-spacing:1px">Spot Positions</div>';
  for (const p of positions) {
    const pnlClass = p.pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
    const pnlSign = p.pnl >= 0 ? '+' : '';
    html += `<div class="position-bar" style="margin-bottom:8px">
      <span class="pos-sym">${p.symbol}</span>
      <span class="pos-detail">Entry: ${formatPrice(p.entry)}</span>
      <span class="pos-detail">Now: ${formatPrice(p.price)}</span>
      <span class="pos-pnl ${pnlClass}">${pnlSign}${p.pnl.toFixed(4)} (${pnlSign}${p.pnl_pct.toFixed(2)}%)</span>
      <span class="pos-detail">Signal: <span class="dir-badge dir-${p.direction}">${p.direction}</span></span>
      ${p.sl !== null ? `<span class="pos-detail">SL: ${formatPrice(p.sl)}</span>` : ''}
      ${p.tp !== null ? `<span class="pos-detail">TP: ${formatPrice(p.tp)}</span>` : ''}
    </div>`;
  }
  wrap.innerHTML = html;
}

function renderFuturesPositions(rows) {
  const wrap = document.getElementById('futuresPositionsWrap');
  if (!rows || !rows.length) { wrap.innerHTML = ''; return; }
  let html = '<div style="margin-bottom:8px;color:var(--text2);font-size:12px;text-transform:uppercase;letter-spacing:1px">Futures Positions</div>';
  for (const p of rows) {
    const pnlClass = p.unrealized_pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
    const pnlSign = p.unrealized_pnl >= 0 ? '+' : '';
    html += `<div class="position-bar" style="margin-bottom:8px">
      <span class="pos-sym">${p.symbol}</span>
      <span class="pos-detail">Side: ${p.side}</span>
      <span class="pos-detail">Contracts: ${p.contracts}</span>
      <span class="pos-detail">Entry: ${formatPrice(p.entry)}</span>
      <span class="pos-detail">Mark: ${formatPrice(p.mark)}</span>
      <span class="pos-pnl ${pnlClass}">${pnlSign}${p.unrealized_pnl.toFixed(4)} (${p.pnl_pct.toFixed(2)}%)</span>
    </div>`;
  }
  wrap.innerHTML = html;
}

function renderActivities(rows) {
  const wrap = document.getElementById('activitiesWrap');
  if (!rows || !rows.length) { wrap.innerHTML = ''; return; }
  let html = '<div style="margin-bottom:8px;color:var(--text2);font-size:12px;text-transform:uppercase;letter-spacing:1px">Auto-Trade Activity</div>';
  html += '<div class="position-bar" style="display:block">';
  const top = rows.slice(0, 12);
  for (const a of top) {
    html += `<div class="pos-detail" style="padding:2px 0"><strong>${a.ts || '--'}</strong> [${(a.market || 'spot').toUpperCase()}] ${a.action || ''} ${a.symbol || ''} - ${a.message || ''}</div>`;
  }
  html += '</div>';
  wrap.innerHTML = html;
}

function renderTable(results) {
  const tbody = document.getElementById('tbody');
  let html = '';

  for (const r of results) {
    const rowClass = r.direction === 'BUY' ? 'buy-row' : r.direction === 'SELL' ? 'sell-row' : 'hold-row';
    const sltp = r.sl !== null ? `${formatPrice(r.sl)} / ${formatPrice(r.tp)}` : '--';
    const reasons = r.reasons.map(x => `<li>${x}</li>`).join('');

    html += `<tr class="${rowClass} clickable" onclick="toggleDetail('d-${r.symbol}')">
      <td><strong>${r.symbol}</strong>${r.entry !== null ? ` <span class="${r.pnl >= 0 ? 'pnl-pos' : 'pnl-neg'}" style="font-size:12px">(${r.pnl >= 0 ? '+' : ''}${r.pnl_pct.toFixed(2)}%)</span>` : ''}</td>
      <td>${formatPrice(r.price)}</td>
      <td><span class="dir-badge dir-${r.direction}">${r.direction}</span></td>
      <td>${scorePips(r.score, r.max_score)}</td>
      <td>${Math.round(r.confidence * 100)}%</td>
      <td>${r.rsi}</td>
      <td>${r.macd_hist.toFixed(6)}</td>
      <td>${r.stoch_k}/${r.stoch_d}</td>
      <td>${sltp}</td>
      <td><ul class="reason-list">${reasons}</ul></td>
    </tr>`;

    // Detail row
    html += `<tr class="detail-row" id="d-${r.symbol}"><td colspan="10"><div class="detail-cell"><div class="detail-grid">
      <div class="detail-item"><div class="dlabel">MACD Line</div>${r.macd_line}</div>
      <div class="detail-item"><div class="dlabel">MACD Signal</div>${r.macd_signal}</div>
      <div class="detail-item"><div class="dlabel">ATR</div>${r.atr}</div>
      <div class="detail-item"><div class="dlabel">Bollinger Upper</div>${formatPrice(r.bb_upper)}</div>
      <div class="detail-item"><div class="dlabel">Bollinger Mid</div>${formatPrice(r.bb_mid)}</div>
      <div class="detail-item"><div class="dlabel">Bollinger Lower</div>${formatPrice(r.bb_lower)}</div>
      <div class="detail-item"><div class="dlabel">Stochastic %K</div>${r.stoch_k}</div>
      <div class="detail-item"><div class="dlabel">Stochastic %D</div>${r.stoch_d}</div>
      ${r.trailing !== null ? `<div class="detail-item"><div class="dlabel">Trailing Stop</div>${formatPrice(r.trailing)}</div>` : ''}
    </div></div></td></tr>`;
  }

  tbody.innerHTML = html;
}

function toggleDetail(id) {
  document.getElementById(id).classList.toggle('open');
}

function updateCountdown() {
  if (!nextScanTime) return;
  const diff = Math.max(0, Math.round((nextScanTime - Date.now()) / 1000));
  const m = Math.floor(diff / 60);
  const s = diff % 60;
  document.getElementById('countdown').textContent = `${m}:${String(s).padStart(2, '0')}`;
}

async function refresh() {
  try {
    const resp = await fetch('/api/scan');
    const data = await resp.json();
    const results = data.results || [];

    document.getElementById('lastScan').textContent = data.last_scan;
    document.getElementById('cycle').textContent = data.cycle;
    document.getElementById('symCount').textContent = data.symbols_count;
    document.getElementById('buyCount').textContent = results.filter(r => r.direction === 'BUY').length;
    document.getElementById('sellCount').textContent = results.filter(r => r.direction === 'SELL').length;

    const avgConf = results.length
      ? Math.round(results.reduce((s, r) => s + r.confidence, 0) / results.length * 100) + '%'
      : '--';
    document.getElementById('avgConf').textContent = avgConf;
    const perf = data.performance || {};
    const futPerf = perf.futures || {};
    const spotPerf = perf.spot || {};
    const totalClosed = (futPerf.closed_trades ?? 0) + (spotPerf.closed_trades ?? 0);
    document.getElementById('closedTrades').textContent = totalClosed;
    document.getElementById('spotBuys').textContent = spotPerf.buy_count ?? 0;
    document.getElementById('spotSells').textContent = spotPerf.sell_count ?? 0;
    document.getElementById('spotFullCloses').textContent = spotPerf.full_closed_trades ?? 0;
    document.getElementById('spotRealizedPnl').textContent = `${spotPerf.realized_pnl_usdt ?? 0} USDT`;
    document.getElementById('spotUnrealizedPnl').textContent = `${spotPerf.unrealized_pnl_usdt ?? 0} USDT`;
    document.getElementById('winRate').textContent = `${futPerf.win_rate_pct ?? 0}%`;
    document.getElementById('netPnlPct').textContent = `${futPerf.net_pnl_pct ?? 0}%`;
    document.getElementById('avgPnlPct').textContent = `${futPerf.avg_pnl_pct ?? 0}%`;

    // Parse next scan time
    if (data.next_scan) {
      const today = new Date().toISOString().split('T')[0];
      nextScanTime = new Date(today + 'T' + data.next_scan).getTime();
      if (nextScanTime < Date.now()) nextScanTime += 86400000; // next day
    }

    renderSpotPositions(results);
    renderFuturesPositions(data.futures_positions || []);
    renderActivities(data.activities || []);
    renderTable(results);
  } catch (e) {
    console.error('Refresh error:', e);
  }
}

// Auto-refresh every 15 seconds
setInterval(refresh, 15000);
setInterval(updateCountdown, 1000);
refresh();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="scanner_dashboard",
        description="Unified Scanner — Live Web Dashboard (runs 24/7)",
    )
    p.add_argument("--port", type=int, default=5000, help="HTTP port (default: 5000)")
    p.add_argument("--top", type=int, default=30, help="Scan top N symbols by volume (default: 30)")
    p.add_argument("--exchange", default="binance", help="Exchange (default: binance)")
    p.add_argument("--interval", "-i", default="15m", help="Candle timeframe (default: 15m)")
    p.add_argument("--limit", "-l", type=int, default=120, help="Candle count (default: 120)")
    p.add_argument("--sleep", type=int, default=5, help="Minutes between scan cycles (default: 5)")
    p.add_argument(
        "--entry", nargs="+", metavar="SYM=PRICE",
        help="Manually track positions (e.g. --entry SOL=87.70). Auto-fetches from Bitget too.",
    )
    p.add_argument(
        "--no-telegram", action="store_true",
        help="Disable Telegram alerts even if credentials are in .env.",
    )
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )
    # Keep ccxt quiet
    logging.getLogger("ccxt").setLevel(logging.WARNING)

    # Disable telegram if requested
    if args.no_telegram:
        os.environ["TELEGRAM_BOT_TOKEN"] = ""

    # Parse manual entry prices (on top of auto-fetched ones)
    if args.entry:
        for pair in args.entry:
            sym, price = pair.split("=")
            state.entry_prices[sym.upper()] = float(price)

    # Start background scanner thread
    scanner_thread = threading.Thread(
        target=_scan_cycle,
        args=(args.exchange, args.top, args.interval, args.limit, args.sleep),
        daemon=True,
    )
    scanner_thread.start()

    log.info(
        "Dashboard starting on http://localhost:%d — scanning top %d every %d min",
        args.port, args.top, args.sleep,
    )

    # Run Flask (use_reloader=False because we have our own background thread)
    app.run(host="0.0.0.0", port=args.port, use_reloader=False)


if __name__ == "__main__":
    main()
