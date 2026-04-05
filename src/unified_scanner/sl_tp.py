"""
Stop-loss / Take-profit calculator.

Combines the best approaches from:
- signal_bot/signals/slTpLevels.js   (ATR-based SL/TP with multiplier + trailing)
- signal_bot/signals/slTpLevels.js   (percentage-based fallback)
- src/engine/risk.py                 (daily loss limit pattern)
- futures_risk config                (fixed % SL/TP)

Returns SL/TP prices, trailing stop, and the ATR value used.
"""
from __future__ import annotations

from dataclasses import dataclass

from .indicators import atr


@dataclass
class SlTpResult:
    stop_loss: float
    take_profit: float
    trailing_stop: float | None
    atr_val: float
    method: str  # "atr" or "percent"


# ---------------------------------------------------------------------------
# ATR-based SL/TP  (ported from signal_bot/signals/slTpLevels.js)
# ---------------------------------------------------------------------------

def sl_tp_atr(
    highs: list,
    lows: list,
    closes: list,
    direction: str,
    multiplier: float = 1.5,
    atr_period: int = 14,
    trailing: bool = True,
) -> SlTpResult:
    """
    Calculate ATR-based stop-loss and take-profit levels.

    Adapts to current volatility — wider stops in volatile markets,
    tighter in calm markets.

    Args:
        highs/lows/closes: OHLCV price lists
        direction: "BUY" or "SELL"
        multiplier: ATR multiplier for SL/TP distance (default 1.5)
        atr_period: ATR lookback period
        trailing: whether to include a trailing stop (1x ATR)
    """
    atr_val = atr(highs, lows, closes, atr_period)
    last_close = closes[-1] if closes else 0.0

    if atr_val <= 0 or last_close <= 0:
        # Fallback to percentage-based if ATR unavailable
        return sl_tp_percent(last_close, direction)

    distance = multiplier * atr_val

    if direction.upper() == "BUY":
        sl = last_close - distance
        tp = last_close + distance
        trail = last_close - atr_val if trailing else None
    else:  # SELL
        sl = last_close + distance
        tp = last_close - distance
        trail = last_close + atr_val if trailing else None

    return SlTpResult(
        stop_loss=round(sl, 8),
        take_profit=round(tp, 8),
        trailing_stop=round(trail, 8) if trail is not None else None,
        atr_val=atr_val,
        method="atr",
    )


# ---------------------------------------------------------------------------
# Percentage-based SL/TP  (fallback from signal_bot/signals/slTpLevels.js)
# ---------------------------------------------------------------------------

def sl_tp_percent(
    entry_price: float,
    direction: str,
    sl_pct: float = 0.015,
    tp_pct: float = 0.03,
) -> SlTpResult:
    """
    Fixed percentage-based SL/TP — fallback when ATR is unavailable.

    Args:
        entry_price: current/entry price
        direction: "BUY" or "SELL"
        sl_pct: stop-loss percentage (default 1.5%)
        tp_pct: take-profit percentage (default 3%)
    """
    if entry_price <= 0:
        return SlTpResult(0.0, 0.0, None, 0.0, "percent")

    if direction.upper() == "BUY":
        sl = entry_price * (1 - sl_pct)
        tp = entry_price * (1 + tp_pct)
    else:
        sl = entry_price * (1 + sl_pct)
        tp = entry_price * (1 - tp_pct)

    return SlTpResult(
        stop_loss=round(sl, 8),
        take_profit=round(tp, 8),
        trailing_stop=None,
        atr_val=0.0,
        method="percent",
    )


# ---------------------------------------------------------------------------
# Combined: try ATR first, fall back to percent
# ---------------------------------------------------------------------------

def compute_sl_tp(
    klines: list,
    direction: str,
    scanner_cfg: dict | None = None,
) -> SlTpResult:
    """
    Compute SL/TP using the best available method.
    Tries ATR-based first; falls back to percentage-based.

    Args:
        klines: OHLCV list [[ts, open, high, low, close, vol, ...], ...]
        direction: "BUY" or "SELL"
        scanner_cfg: optional config dict
    """
    cfg = scanner_cfg or {}
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    closes = [float(k[4]) for k in klines]

    multiplier = float(cfg.get("atr_sl_tp_multiplier", 1.5))
    atr_period = int(cfg.get("atr_period", 14))
    trailing = bool(cfg.get("trailing_stop_enabled", True))
    sl_pct = float(cfg.get("fallback_sl_pct", 0.015))
    tp_pct = float(cfg.get("fallback_tp_pct", 0.03))

    result = sl_tp_atr(highs, lows, closes, direction, multiplier, atr_period, trailing)

    # If ATR method failed (returned percent fallback with 0 atr), use configured pcts
    if result.method == "percent":
        entry = closes[-1] if closes else 0.0
        result = sl_tp_percent(entry, direction, sl_pct, tp_pct)

    return result
