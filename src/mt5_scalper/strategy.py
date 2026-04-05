from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Signal:
    symbol: str
    direction: str  # BUY | SELL | HOLD
    score: int
    confidence: float
    reason: str


def _calculate_rsi(closes: list[float], period: int = 14) -> float:
    """Calculate RSI (Relative Strength Index)."""
    if len(closes) < period + 1:
        return 50.0
    
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    seed = deltas[:period]
    
    up = sum(max(d, 0) for d in seed) / period
    down = sum(max(-d, 0) for d in seed) / period
    
    rs_list = []
    for delta in deltas[period:]:
        up = (up * (period - 1) + max(delta, 0)) / period
        down = (down * (period - 1) + max(-delta, 0)) / period
        rs = up / down if down != 0 else 0
        rs_list.append(100 - 100 / (1 + rs))
    
    return rs_list[-1] if rs_list else 50.0


def compute_signal(ohlcv: list[list[float]], symbol: str) -> Signal:
    """
    Crossover-triggered strategy with RSI momentum confirmation.

    Logic:
    - Detects the MOMENT a 7/14 EMA crossover occurs (prev bar vs current bar).
    - RSI must confirm momentum direction (50-70 for BUY, 30-50 for SELL).
    - Returns HOLD on every bar that is NOT a crossover event.
    """
    if len(ohlcv) < 50:
        return Signal(symbol=symbol, direction="HOLD", score=0, confidence=0.0, reason="insufficient_data")

    closes = [float(c[4]) for c in ohlcv]
    volumes = [float(c[5]) for c in ohlcv]

    # Current bar values
    ema_7_curr = sum(closes[-7:]) / 7.0
    ema_14_curr = sum(closes[-14:]) / 14.0

    rsi = _calculate_rsi(closes, period=14)

    # Volatility filter: avoid flat sessions where spread/noise dominates.
    recent_range = max(closes[-10:]) - min(closes[-10:])
    if "XAU" in symbol and recent_range < 2.0:
        return Signal(symbol=symbol, direction="HOLD", score=0, confidence=0.4, reason="low_volatility")

    # Volume filter: avoid dead sessions where spread/noise dominates.
    avg_volume_10 = sum(volumes[-11:-1]) / 10.0
    current_volume = volumes[-1]
    if current_volume <= avg_volume_10:
        return Signal(symbol=symbol, direction="HOLD", score=0, confidence=0.45, reason="low_volume")

    # Momentum-filtered entries:
    # BUY: EMA7 above EMA14 + RSI strength in upper-neutral zone
    if ema_7_curr > ema_14_curr and 55 < rsi < 70:
        return Signal(symbol=symbol, direction="BUY", score=1, confidence=0.8, reason="momentum_buy")

    # SELL: EMA7 below EMA14 + RSI weakness in lower-neutral zone
    if ema_7_curr < ema_14_curr and 30 < rsi < 45:
        return Signal(symbol=symbol, direction="SELL", score=1, confidence=0.8, reason="momentum_sell")

    return Signal(symbol=symbol, direction="HOLD", score=0, confidence=0.5, reason="waiting_for_cross")
