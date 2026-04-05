"""
Unified technical indicator library.

Combines the best implementations from ALL scanners found on this machine:
- src/futures/indicators.py         (RSI with NaN safety, SMA)
- signal_bot/indicators/macd.js     (MACD: fast=12, slow=26, signal=9 EMA)
- signal_bot/indicators/atr.js      (ATR: True Range with prev-close)
- dual_strategy_with_RSI.py         (spread noise, recent high/low, dual MA)
- adaptive_htf_bias.py              (Bollinger Bands mid for bias scoring)
- signal_bot/signalEngine.js        (EMA helper)
- C:\\Users\\Administrator\\indicators\\indicators.py       (Ichimoku Cloud, Laguerre RSI)
- C:\\Users\\Administrator\\indicators\\indicators (2).py   (QTPyLib: Stochastic, Heikin-Ashi,
      Keltner Channel, VWAP, HMA, crossover detection, Wilder RSI)
- C:\\Users\\Administrator\\indicators\\indicators (5).py   (Pure-list Wilder-smoothed RSI/ATR)
- C:\\Users\\Administrator\\indicators\\ws_indicators.py    (EWM Wilder RSI/ATR upgrade)

All functions accept pandas Series or plain lists and return floats/dicts.
No external TA library required — manual implementations with pandas/numpy.
"""
from __future__ import annotations

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Moving Averages
# ---------------------------------------------------------------------------

def sma(series: pd.Series | list, length: int) -> float:
    """Simple Moving Average — returns latest value."""
    if isinstance(series, list):
        series = pd.Series(series, dtype=float)
    if series is None or len(series) < max(1, length):
        return 0.0
    return float(series.rolling(length).mean().iloc[-1])


def ema(series: pd.Series | list, length: int) -> pd.Series:
    """Exponential Moving Average — returns full series."""
    if isinstance(series, list):
        series = pd.Series(series, dtype=float)
    if series is None or len(series) < length:
        return pd.Series(dtype=float)
    return series.ewm(span=length, adjust=False).mean()


# ---------------------------------------------------------------------------
# RSI  (upgraded to Wilder EWM smoothing from ws_indicators.py)
# ---------------------------------------------------------------------------

def rsi(series: pd.Series | list, length: int = 14) -> float:
    """Relative Strength Index (0-100). Returns latest value.
    Uses Wilder EWM smoothing (alpha=1/length) — industry standard."""
    if isinstance(series, list):
        series = pd.Series(series, dtype=float)
    if series is None or len(series) < length + 1:
        return 50.0
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    value = 100 - (100 / (1 + rs))
    latest = value.iloc[-1]
    if pd.isna(latest):
        return 50.0
    return float(latest)


def rsi_series(series: pd.Series | list, length: int = 14) -> pd.Series:
    """RSI as full series (needed for divergence detection).
    Uses Wilder EWM smoothing."""
    if isinstance(series, list):
        series = pd.Series(series, dtype=float)
    if series is None or len(series) < length + 1:
        return pd.Series(dtype=float)
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ---------------------------------------------------------------------------
# MACD  (ported from signal_bot/indicators/macd.js)
# ---------------------------------------------------------------------------

def macd(
    series: pd.Series | list,
    fast: int = 12,
    slow: int = 26,
    signal_len: int = 9,
) -> dict:
    """
    MACD indicator.

    Returns dict with keys:
      macd_line  — MACD line (fast EMA - slow EMA), latest float
      signal     — signal line (EMA of MACD), latest float
      histogram  — MACD - signal, latest float
      macd_series, signal_series, histogram_series — full pd.Series
    """
    if isinstance(series, list):
        series = pd.Series(series, dtype=float)
    if series is None or len(series) < slow + signal_len:
        return {
            "macd_line": 0.0, "signal": 0.0, "histogram": 0.0,
            "macd_series": pd.Series(dtype=float),
            "signal_series": pd.Series(dtype=float),
            "histogram_series": pd.Series(dtype=float),
        }

    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal_len)
    hist = macd_line - signal_line

    return {
        "macd_line": float(macd_line.iloc[-1]),
        "signal": float(signal_line.iloc[-1]),
        "histogram": float(hist.iloc[-1]),
        "macd_series": macd_line,
        "signal_series": signal_line,
        "histogram_series": hist,
    }


# ---------------------------------------------------------------------------
# ATR  (upgraded to Wilder EWM smoothing from ws_indicators.py)
# ---------------------------------------------------------------------------

def atr(
    highs: pd.Series | list,
    lows: pd.Series | list,
    closes: pd.Series | list,
    length: int = 14,
) -> float:
    """Average True Range — returns latest value.
    Uses Wilder EWM smoothing (alpha=1/length) — more responsive."""
    if isinstance(highs, list):
        highs = pd.Series(highs, dtype=float)
    if isinstance(lows, list):
        lows = pd.Series(lows, dtype=float)
    if isinstance(closes, list):
        closes = pd.Series(closes, dtype=float)

    if len(highs) < length + 1 or len(lows) < length + 1 or len(closes) < length + 1:
        return 0.0

    prev_close = closes.shift(1)
    tr = pd.concat([
        highs - lows,
        (highs - prev_close).abs(),
        (lows - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr_val = tr.ewm(alpha=1 / length, adjust=False).mean().iloc[-1]
    if pd.isna(atr_val):
        return 0.0
    return float(atr_val)


def atr_series(
    highs: pd.Series | list,
    lows: pd.Series | list,
    closes: pd.Series | list,
    length: int = 14,
) -> pd.Series:
    """ATR as full series (needed for average-ATR comparisons).
    Uses Wilder EWM smoothing."""
    if isinstance(highs, list):
        highs = pd.Series(highs, dtype=float)
    if isinstance(lows, list):
        lows = pd.Series(lows, dtype=float)
    if isinstance(closes, list):
        closes = pd.Series(closes, dtype=float)

    if len(highs) < length + 1:
        return pd.Series(dtype=float)

    prev_close = closes.shift(1)
    tr = pd.concat([
        highs - lows,
        (highs - prev_close).abs(),
        (lows - prev_close).abs(),
    ], axis=1).max(axis=1)

    return tr.ewm(alpha=1 / length, adjust=False).mean()


# ---------------------------------------------------------------------------
# ADX / DMI  (trend strength filter)
# ---------------------------------------------------------------------------

def adx(
    highs: pd.Series | list,
    lows: pd.Series | list,
    closes: pd.Series | list,
    length: int = 14,
) -> float:
    """
    Average Directional Index (ADX) — trend strength (0..100), no direction.
    Typical interpretation: ADX < 20 weak/range, ADX > 20 stronger trend.
    """
    if isinstance(highs, list):
        highs = pd.Series(highs, dtype=float)
    if isinstance(lows, list):
        lows = pd.Series(lows, dtype=float)
    if isinstance(closes, list):
        closes = pd.Series(closes, dtype=float)

    if len(highs) < length + 2 or len(lows) < length + 2 or len(closes) < length + 2:
        return 0.0

    up_move = highs.diff()
    down_move = -lows.diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    prev_close = closes.shift(1)
    tr = pd.concat(
        [
            highs - lows,
            (highs - prev_close).abs(),
            (lows - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr_s = tr.ewm(alpha=1 / length, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr_s.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr_s.replace(0, np.nan)

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0.0)
    adx_val = dx.ewm(alpha=1 / length, adjust=False).mean().iloc[-1]
    if pd.isna(adx_val):
        return 0.0
    return float(adx_val)


# ---------------------------------------------------------------------------
# Bollinger Bands  (referenced in adaptive_htf_bias.py for bias scoring)
# ---------------------------------------------------------------------------

def bollinger_bands(
    series: pd.Series | list,
    length: int = 20,
    std_dev: float = 2.0,
) -> dict:
    """
    Bollinger Bands — returns latest upper, mid, lower, and bandwidth.
    """
    if isinstance(series, list):
        series = pd.Series(series, dtype=float)
    if series is None or len(series) < length:
        return {"upper": 0.0, "mid": 0.0, "lower": 0.0, "bandwidth": 0.0}

    mid = series.rolling(length).mean()
    std = series.rolling(length).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std

    mid_val = float(mid.iloc[-1]) if not pd.isna(mid.iloc[-1]) else 0.0
    upper_val = float(upper.iloc[-1]) if not pd.isna(upper.iloc[-1]) else 0.0
    lower_val = float(lower.iloc[-1]) if not pd.isna(lower.iloc[-1]) else 0.0
    bw = (upper_val - lower_val) / mid_val if mid_val > 0 else 0.0

    return {"upper": upper_val, "mid": mid_val, "lower": lower_val, "bandwidth": bw}


# ---------------------------------------------------------------------------
# Spread Noise  (from dual_strategy_with_RSI.py — volatility ceiling filter)
# ---------------------------------------------------------------------------

def spread_noise(
    highs: pd.Series | list,
    lows: pd.Series | list,
    closes: pd.Series | list,
) -> float:
    """
    Spread noise = (high - low) / close for the latest bar.
    Used as a volatility ceiling — values > 0.01 often indicate too-noisy markets.
    """
    if isinstance(highs, list):
        highs = pd.Series(highs, dtype=float)
    if isinstance(lows, list):
        lows = pd.Series(lows, dtype=float)
    if isinstance(closes, list):
        closes = pd.Series(closes, dtype=float)
    if len(closes) == 0:
        return 0.0
    c = float(closes.iloc[-1])
    if c <= 0:
        return 0.0
    return float((highs.iloc[-1] - lows.iloc[-1]) / c)


# ---------------------------------------------------------------------------
# Recent High / Low  (from dual_strategy_with_RSI.py — loss cap filter)
# ---------------------------------------------------------------------------

def recent_high_low(
    closes: pd.Series | list,
    window: int = 10,
) -> dict:
    """
    Rolling high/low over `window` bars. Used for expected-move and loss-cap checks.
    Returns latest recent_high, recent_low, and expected_move ratio.
    """
    if isinstance(closes, list):
        closes = pd.Series(closes, dtype=float)
    if len(closes) < window:
        return {"recent_high": 0.0, "recent_low": 0.0, "expected_move": 0.0}

    rh = float(closes.rolling(window).max().iloc[-1])
    rl = float(closes.rolling(window).min().iloc[-1])
    last = float(closes.iloc[-1])
    em = (rh - rl) / last if last > 0 else 0.0
    return {"recent_high": rh, "recent_low": rl, "expected_move": em}


# ---------------------------------------------------------------------------
# Ichimoku Cloud  (from C:\Users\Administrator\indicators\indicators.py)
# ---------------------------------------------------------------------------

def ichimoku(
    highs: pd.Series | list,
    lows: pd.Series | list,
    closes: pd.Series | list,
    conversion_period: int = 9,
    base_period: int = 26,
    lagging_span: int = 52,
    displacement: int = 26,
) -> dict:
    """
    Ichimoku Cloud indicator.

    Returns dict with latest values for:
      tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b,
      cloud_green (bool), cloud_red (bool)
    """
    if isinstance(highs, list):
        highs = pd.Series(highs, dtype=float)
    if isinstance(lows, list):
        lows = pd.Series(lows, dtype=float)
    if isinstance(closes, list):
        closes = pd.Series(closes, dtype=float)

    empty = {
        "tenkan_sen": 0.0, "kijun_sen": 0.0,
        "senkou_span_a": 0.0, "senkou_span_b": 0.0,
        "cloud_green": False, "cloud_red": False,
    }
    if len(highs) < lagging_span:
        return empty

    tenkan = (highs.rolling(conversion_period).max() + lows.rolling(conversion_period).min()) / 2
    kijun = (highs.rolling(base_period).max() + lows.rolling(base_period).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(displacement - 1)
    span_b = ((highs.rolling(lagging_span).max() + lows.rolling(lagging_span).min()) / 2).shift(
        displacement - 1
    )

    def _last(s):
        v = s.iloc[-1]
        return float(v) if not pd.isna(v) else 0.0

    sa, sb = _last(span_a), _last(span_b)
    return {
        "tenkan_sen": _last(tenkan),
        "kijun_sen": _last(kijun),
        "senkou_span_a": sa,
        "senkou_span_b": sb,
        "cloud_green": sa > sb,
        "cloud_red": sb > sa,
    }


# ---------------------------------------------------------------------------
# Stochastic Oscillator  (from indicators (2).py — QTPyLib)
# ---------------------------------------------------------------------------

def stochastic(
    highs: pd.Series | list,
    lows: pd.Series | list,
    closes: pd.Series | list,
    window: int = 14,
    smooth_k: int = 3,
    smooth_d: int = 3,
) -> dict:
    """
    Stochastic Oscillator — returns slow %K and slow %D (0-100).
    """
    if isinstance(highs, list):
        highs = pd.Series(highs, dtype=float)
    if isinstance(lows, list):
        lows = pd.Series(lows, dtype=float)
    if isinstance(closes, list):
        closes = pd.Series(closes, dtype=float)

    if len(closes) < window + smooth_k:
        return {"k": 50.0, "d": 50.0}

    rolling_high = highs.rolling(window).max()
    rolling_low = lows.rolling(window).min()
    denom = rolling_high - rolling_low
    fast_k = 100 * (closes - rolling_low) / denom.replace(0, np.nan)
    slow_k = fast_k.rolling(smooth_k).mean()
    slow_d = slow_k.rolling(smooth_d).mean()

    k_val = slow_k.iloc[-1]
    d_val = slow_d.iloc[-1]
    return {
        "k": float(k_val) if not pd.isna(k_val) else 50.0,
        "d": float(d_val) if not pd.isna(d_val) else 50.0,
    }


# ---------------------------------------------------------------------------
# Heikin-Ashi  (from indicators (2).py — QTPyLib)
# ---------------------------------------------------------------------------

def heikinashi(
    opens: pd.Series | list,
    highs: pd.Series | list,
    lows: pd.Series | list,
    closes: pd.Series | list,
) -> dict:
    """
    Heikin-Ashi candle transformation.
    Returns dict with ha_open, ha_high, ha_low, ha_close (all pd.Series).
    """
    if isinstance(opens, list):
        opens = pd.Series(opens, dtype=float)
    if isinstance(highs, list):
        highs = pd.Series(highs, dtype=float)
    if isinstance(lows, list):
        lows = pd.Series(lows, dtype=float)
    if isinstance(closes, list):
        closes = pd.Series(closes, dtype=float)

    ha_close = (opens + highs + lows + closes) / 4

    ha_open = pd.Series(np.zeros(len(opens)), dtype=float)
    ha_open.iloc[0] = (float(opens.iloc[0]) + float(closes.iloc[0])) / 2
    for i in range(1, len(opens)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2

    ha_high = pd.concat([highs, ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([lows, ha_open, ha_close], axis=1).min(axis=1)

    return {
        "ha_open": ha_open,
        "ha_high": ha_high,
        "ha_low": ha_low,
        "ha_close": ha_close,
    }


# ---------------------------------------------------------------------------
# Keltner Channel  (from indicators (2).py — QTPyLib)
# ---------------------------------------------------------------------------

def keltner_channel(
    highs: pd.Series | list,
    lows: pd.Series | list,
    closes: pd.Series | list,
    window: int = 14,
    atr_mult: float = 2.0,
) -> dict:
    """
    Keltner Channel — ATR-based volatility channel around typical price.
    Returns dict with upper, mid, lower (latest float values).
    """
    if isinstance(highs, list):
        highs = pd.Series(highs, dtype=float)
    if isinstance(lows, list):
        lows = pd.Series(lows, dtype=float)
    if isinstance(closes, list):
        closes = pd.Series(closes, dtype=float)

    if len(closes) < window + 1:
        return {"upper": 0.0, "mid": 0.0, "lower": 0.0}

    typical = (highs + lows + closes) / 3
    mid = typical.rolling(window).mean()
    atr_val = atr_series(highs, lows, closes, window) * atr_mult

    upper_s = mid + atr_val
    lower_s = mid - atr_val

    def _last(s):
        v = s.iloc[-1]
        return float(v) if not pd.isna(v) else 0.0

    return {"upper": _last(upper_s), "mid": _last(mid), "lower": _last(lower_s)}


# ---------------------------------------------------------------------------
# Rolling VWAP  (from indicators (2).py — QTPyLib)
# ---------------------------------------------------------------------------

def rolling_vwap(
    highs: pd.Series | list,
    lows: pd.Series | list,
    closes: pd.Series | list,
    volumes: pd.Series | list,
    window: int = 20,
) -> float:
    """
    Volume-weighted average price over a rolling window. Returns latest value.
    """
    if isinstance(highs, list):
        highs = pd.Series(highs, dtype=float)
    if isinstance(lows, list):
        lows = pd.Series(lows, dtype=float)
    if isinstance(closes, list):
        closes = pd.Series(closes, dtype=float)
    if isinstance(volumes, list):
        volumes = pd.Series(volumes, dtype=float)

    if len(closes) < window:
        return 0.0

    typical = (highs + lows + closes) / 3
    vol_tp = (volumes * typical).rolling(window).sum()
    vol_sum = volumes.rolling(window).sum()
    vwap_s = vol_tp / vol_sum.replace(0, np.nan)

    val = vwap_s.iloc[-1]
    return float(val) if not pd.isna(val) else 0.0


# ---------------------------------------------------------------------------
# Hull Moving Average  (from indicators (2).py — QTPyLib)
# ---------------------------------------------------------------------------

def hma(series: pd.Series | list, length: int = 20) -> float:
    """
    Hull Moving Average — faster-responding MA with reduced lag.
    Returns latest value.
    """
    if isinstance(series, list):
        series = pd.Series(series, dtype=float)
    if series is None or len(series) < length:
        return 0.0

    half_len = max(1, length // 2)
    sqrt_len = max(1, int(np.sqrt(length)))
    wma_half = series.ewm(span=half_len, adjust=False).mean()
    wma_full = series.ewm(span=length, adjust=False).mean()
    diff = 2 * wma_half - wma_full
    hull = diff.ewm(span=sqrt_len, adjust=False).mean()

    val = hull.iloc[-1]
    return float(val) if not pd.isna(val) else 0.0


# ---------------------------------------------------------------------------
# Crossover Detection  (from indicators (2).py — QTPyLib)
# ---------------------------------------------------------------------------

def crossed_above(series1: pd.Series, series2: pd.Series | float) -> pd.Series:
    """True on bars where series1 crosses above series2."""
    if isinstance(series2, (float, int)):
        series2 = pd.Series(series2, index=series1.index)
    return (series1 > series2) & (series1.shift(1) <= series2.shift(1))


def crossed_below(series1: pd.Series, series2: pd.Series | float) -> pd.Series:
    """True on bars where series1 crosses below series2."""
    if isinstance(series2, (float, int)):
        series2 = pd.Series(series2, index=series1.index)
    return (series1 < series2) & (series1.shift(1) >= series2.shift(1))


# ---------------------------------------------------------------------------
# Laguerre RSI  (from C:\Users\Administrator\indicators\indicators.py)
#               Author: Creslin  /  Original: John Ehlers 1979
# ---------------------------------------------------------------------------

def laguerre_rsi(closes: pd.Series | list, gamma: float = 0.75) -> float:
    """
    Laguerre RSI — noise-filtered RSI variant (0.0 to 1.0).
    Buy when flat at 0, sell on drop from 1.
    """
    if isinstance(closes, list):
        closes = pd.Series(closes, dtype=float)
    if closes is None or len(closes) < 4:
        return 0.5

    g = gamma
    L0 = L1 = L2 = L3 = 0.0
    lrsi_val = 0.0

    for price in closes:
        L0_1, L1_1, L2_1, L3_1 = L0, L1, L2, L3
        L0 = (1 - g) * float(price) + g * L0_1
        L1 = -g * L0 + L0_1 + g * L1_1
        L2 = -g * L1 + L1_1 + g * L2_1
        L3 = -g * L2 + L2_1 + g * L3_1

        cu = cd = 0.0
        cu += (L0 - L1) if L0 >= L1 else 0.0
        cd += (L1 - L0) if L0 < L1 else 0.0
        cu += (L1 - L2) if L1 >= L2 else 0.0
        cd += (L2 - L1) if L1 < L2 else 0.0
        cu += (L2 - L3) if L2 >= L3 else 0.0
        cd += (L3 - L2) if L2 < L3 else 0.0

        lrsi_val = cu / (cu + cd) if (cu + cd) != 0 else 0.0

    return lrsi_val
