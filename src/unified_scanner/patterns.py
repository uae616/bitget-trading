"""
Price pattern & structural detectors.

Combines the best from:
- signal_bot/signals/patterns.js   (engulfing candlestick patterns)
- signal_bot/signals/breakout.js   (N-bar breakout)
- signal_bot/core/signals/signalEngine.js  (RSI divergence, MACD histogram expansion)

All functions work with OHLCV lists in the same format KlineScanner already fetches:
  [ [openTime, open, high, low, close, volume, ...], ... ]
"""
from __future__ import annotations

import pandas as pd
from .indicators import rsi_series, macd


# ---------------------------------------------------------------------------
# Candlestick Patterns  (ported from signal_bot/signals/patterns.js)
# ---------------------------------------------------------------------------

def detect_engulfing(klines: list) -> str | None:
    """
    Detect bullish or bearish engulfing on the last two candles.

    Returns 'BULLISH_ENGULFING', 'BEARISH_ENGULFING', or None.
    Kline format: [timestamp, open, high, low, close, volume, ...]
    """
    if len(klines) < 2:
        return None

    prev = klines[-2]
    curr = klines[-1]

    prev_open, prev_close = float(prev[1]), float(prev[4])
    curr_open, curr_close = float(curr[1]), float(curr[4])

    prev_red = prev_close < prev_open
    prev_green = prev_close > prev_open
    curr_red = curr_close < curr_open
    curr_green = curr_close > curr_open

    # Bullish engulfing: prev red, curr green body fully engulfs prev body
    if prev_red and curr_green:
        if curr_close > prev_open and curr_open < prev_close:
            return "BULLISH_ENGULFING"

    # Bearish engulfing: prev green, curr red body fully engulfs prev body
    if prev_green and curr_red:
        if curr_close < prev_open and curr_open > prev_close:
            return "BEARISH_ENGULFING"

    return None


# ---------------------------------------------------------------------------
# Breakout Detection  (ported from signal_bot/signals/breakout.js)
# ---------------------------------------------------------------------------

def detect_breakout(closes: list | pd.Series, lookback: int = 20) -> str | None:
    """
    Detect N-bar high/low breakout.

    Returns 'BREAKOUT_UP', 'BREAKOUT_DOWN', or None.
    """
    if isinstance(closes, pd.Series):
        closes = closes.tolist()
    if len(closes) < lookback + 1:
        return None

    # Window excludes the current candle
    window = closes[-(lookback + 1):-1]
    last = closes[-1]
    highest = max(window)
    lowest = min(window)

    if last > highest:
        return "BREAKOUT_UP"
    if last < lowest:
        return "BREAKOUT_DOWN"
    return None


# ---------------------------------------------------------------------------
# RSI Divergence  (ported from signal_bot/core/signals/signalEngine.js)
# ---------------------------------------------------------------------------

def detect_rsi_divergence(
    closes: list | pd.Series,
    rsi_length: int = 14,
    lookback: int = 10,
) -> str | None:
    """
    Detect RSI divergence over the recent `lookback` bars.

    Bullish divergence: price making lower lows while RSI making higher lows.
    Bearish divergence: price making higher highs while RSI making lower highs.

    Returns 'BULLISH_DIVERGENCE', 'BEARISH_DIVERGENCE', or None.
    """
    if isinstance(closes, list):
        closes = pd.Series(closes, dtype=float)
    if len(closes) < rsi_length + lookback:
        return None

    rsi_vals = rsi_series(closes, rsi_length)
    if rsi_vals.empty:
        return None

    recent_close = closes.iloc[-lookback:]
    recent_rsi = rsi_vals.iloc[-lookback:]

    # Drop NaN from RSI warm-up
    valid = recent_rsi.dropna()
    if len(valid) < 2:
        return None

    # Compare start vs end of window
    price_start = float(recent_close.iloc[0])
    price_end = float(recent_close.iloc[-1])
    rsi_start = float(valid.iloc[0])
    rsi_end = float(valid.iloc[-1])

    price_falling = price_end < price_start
    price_rising = price_end > price_start
    rsi_rising = rsi_end > rsi_start
    rsi_falling = rsi_end < rsi_start

    # Bullish: price falling but RSI rising (momentum recovering)
    if price_falling and rsi_rising:
        return "BULLISH_DIVERGENCE"

    # Bearish: price rising but RSI falling (momentum fading)
    if price_rising and rsi_falling:
        return "BEARISH_DIVERGENCE"

    return None


# ---------------------------------------------------------------------------
# MACD Histogram Expansion  (ported from signal_bot/core/signals/signalEngine.js)
# ---------------------------------------------------------------------------

def is_histogram_expanding(
    closes: list | pd.Series,
    window: int = 3,
    fast: int = 12,
    slow: int = 26,
    signal_len: int = 9,
) -> bool:
    """
    Check if the MACD histogram has been expanding over the last `window` bars.
    A growing histogram confirms trend momentum.
    """
    if isinstance(closes, list):
        closes = pd.Series(closes, dtype=float)

    m = macd(closes, fast, slow, signal_len)
    hist = m["histogram_series"]
    if hist.empty or len(hist) < window + 1:
        return False

    recent = hist.iloc[-window:].tolist()
    # Check absolute values are increasing (expanding regardless of direction)
    for i in range(1, len(recent)):
        if abs(recent[i]) <= abs(recent[i - 1]):
            return False
    return True
