"""
Multi-factor signal scoring engine.

Combines the best scoring logic from:
- signal_bot/core/signals/signalEngine.js  (7-point scoring, divergence, histogram)
- signal_bot/signals/scoreSignal.js        (simple multi-indicator aggregation)
- dual_strategy_with_RSI.py                (strategy classification, noise filter)
- adaptive_htf_bias.py                     (adaptive bias tightening)
- src/engine/strategy.py                   (momentum z-score ranking)
- src/engine/scanner.py                    (multi-horizon momentum)

Returns a SignalResult dataclass with direction, score, confidence, reasons,
and all indicator values.  All thresholds configurable via cfg dict.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.engine.indicators import (
    rsi,
    sma,
    macd,
    atr,
    atr_series,
    bollinger_bands,
    spread_noise,
    recent_high_low,
)
from src.engine.patterns import (
    detect_engulfing,
    detect_breakout,
    detect_rsi_divergence,
    is_histogram_expanding,
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SignalResult:
    direction: str  # "BUY", "SELL", or "HOLD"
    score: int  # 0..max_score
    max_score: int
    confidence: float  # score / max_score
    reasons: list[str] = field(default_factory=list)
    # Indicator values for downstream consumers
    rsi: float = 50.0
    macd_line: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    atr_val: float = 0.0
    sma_val: float = 0.0
    bollinger_mid: float = 0.0
    spread_noise_val: float = 0.0
    pattern: str | None = None
    breakout: str | None = None
    divergence: str | None = None
    histogram_expanding: bool = False
    momentum_z: float = 0.0


# ---------------------------------------------------------------------------
# Default thresholds (overridden by cfg["scanner"] from config.toml)
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "rsi_momentum_low": 40,
    "rsi_momentum_high": 70,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal_len": 9,
    "atr_period": 14,
    "atr_avg_window": 20,
    "ma_len": 50,
    "bb_length": 20,
    "bb_std": 2.0,
    "breakout_lookback": 20,
    "divergence_lookback": 10,
    "histogram_window": 3,
    "noise_ceiling": 0.01,
    "min_expected_move": 0.005,
    "min_score_for_signal": 4,
    "enable_patterns": True,
    "enable_breakout": True,
    "enable_divergence": True,
    "enable_noise_filter": True,
    "enable_bollinger": True,
}


def _cfg(scanner_cfg: dict, key: str):
    return scanner_cfg.get(key, _DEFAULTS[key])


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------

def score_signal(
    klines: list,
    scanner_cfg: dict | None = None,
    momentum_z: float = 0.0,
) -> SignalResult:
    """
    Score a single coin using all available indicators and patterns.

    Args:
        klines: OHLCV list [[ts, open, high, low, close, vol, ...], ...]
        scanner_cfg: dict from config.toml [scanner] section (optional)
        momentum_z: pre-computed momentum z-score from KlineScanner (optional)

    Returns:
        SignalResult with direction, score, confidence, reasons, and indicator values.
    """
    cfg = scanner_cfg or {}
    max_score = 0
    score = 0
    buy_score = 0
    sell_score = 0
    reasons: list[str] = []

    # --- Extract OHLCV series ---
    if len(klines) < 50:
        return SignalResult(
            direction="HOLD", score=0, max_score=1, confidence=0.0,
            reasons=["Insufficient data (need 50+ candles)"],
        )

    closes = [float(k[4]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    close_s = pd.Series(closes, dtype=float)

    # ================================================================
    # 1. RSI  (from futures/indicators.py — best NaN handling)
    # ================================================================
    rsi_len = _cfg(cfg, "rsi_period")
    rsi_val = rsi(close_s, rsi_len)
    rsi_os = _cfg(cfg, "rsi_oversold")
    rsi_ob = _cfg(cfg, "rsi_overbought")

    max_score += 1
    if rsi_val < rsi_os:
        buy_score += 1
        reasons.append(f"RSI oversold ({rsi_val:.1f} < {rsi_os})")
    elif rsi_val > rsi_ob:
        sell_score += 1
        reasons.append(f"RSI overbought ({rsi_val:.1f} > {rsi_ob})")

    # RSI momentum zone  (from signalEngine.js)
    rsi_m_lo = _cfg(cfg, "rsi_momentum_low")
    rsi_m_hi = _cfg(cfg, "rsi_momentum_high")
    max_score += 1
    if rsi_m_lo < rsi_val < rsi_m_hi:
        buy_score += 1
        reasons.append(f"RSI in momentum zone ({rsi_val:.1f})")
    elif rsi_val > rsi_m_hi:
        sell_score += 1
        reasons.append(f"RSI above momentum zone ({rsi_val:.1f})")

    # ================================================================
    # 2. RSI Divergence  (from signalEngine.js — unique)
    # ================================================================
    if _cfg(cfg, "enable_divergence"):
        max_score += 1
        div = detect_rsi_divergence(closes, rsi_len, _cfg(cfg, "divergence_lookback"))
        if div == "BULLISH_DIVERGENCE":
            buy_score += 1
            reasons.append("RSI bullish divergence")
        elif div == "BEARISH_DIVERGENCE":
            sell_score += 1
            reasons.append("RSI bearish divergence")
    else:
        div = None

    # ================================================================
    # 3. MACD Crossover  (from signal_bot/macd.js)
    # ================================================================
    m = macd(close_s, _cfg(cfg, "macd_fast"), _cfg(cfg, "macd_slow"), _cfg(cfg, "macd_signal_len"))
    max_score += 1
    if m["macd_line"] > m["signal"]:
        buy_score += 1
        reasons.append("MACD bullish crossover")
    elif m["macd_line"] < m["signal"]:
        sell_score += 1
        reasons.append("MACD bearish crossover")

    # ================================================================
    # 4. MACD Histogram Expanding  (from signalEngine.js — unique)
    # ================================================================
    max_score += 1
    hist_exp = is_histogram_expanding(closes, _cfg(cfg, "histogram_window"),
                                       _cfg(cfg, "macd_fast"), _cfg(cfg, "macd_slow"),
                                       _cfg(cfg, "macd_signal_len"))
    if hist_exp:
        # Expanding histogram confirms whichever direction MACD points
        if m["histogram"] > 0:
            buy_score += 1
        else:
            sell_score += 1
        reasons.append("MACD histogram expanding")

    # ================================================================
    # 5. ATR above average  (from signalEngine.js — volatility = opportunity)
    # ================================================================
    atr_len = _cfg(cfg, "atr_period")
    atr_val = atr(highs, lows, closes, atr_len)
    atr_full = atr_series(highs, lows, closes, atr_len)
    max_score += 1
    if not atr_full.empty and len(atr_full) >= _cfg(cfg, "atr_avg_window"):
        avg_atr = float(atr_full.iloc[-_cfg(cfg, "atr_avg_window"):].mean())
        if avg_atr > 0 and atr_val > avg_atr:
            # ATR confirms volatility — supports either direction
            if buy_score >= sell_score:
                buy_score += 1
            else:
                sell_score += 1
            reasons.append(f"ATR above average ({atr_val:.4f} > {avg_atr:.4f})")

    # ================================================================
    # 6. Engulfing Pattern  (from signal_bot/patterns.js)
    # ================================================================
    pattern = None
    if _cfg(cfg, "enable_patterns"):
        max_score += 1
        pattern = detect_engulfing(klines)
        if pattern == "BULLISH_ENGULFING":
            buy_score += 1
            reasons.append("Bullish engulfing pattern")
        elif pattern == "BEARISH_ENGULFING":
            sell_score += 1
            reasons.append("Bearish engulfing pattern")

    # ================================================================
    # 7. Breakout Detection  (from signal_bot/breakout.js)
    # ================================================================
    breakout = None
    if _cfg(cfg, "enable_breakout"):
        max_score += 1
        breakout = detect_breakout(closes, _cfg(cfg, "breakout_lookback"))
        if breakout == "BREAKOUT_UP":
            buy_score += 1
            reasons.append(f"Breakout above {_cfg(cfg, 'breakout_lookback')}-bar high")
        elif breakout == "BREAKOUT_DOWN":
            sell_score += 1
            reasons.append(f"Breakout below {_cfg(cfg, 'breakout_lookback')}-bar low")

    # ================================================================
    # 8. Momentum Z-Score  (from KlineScanner — multi-horizon weighted)
    # ================================================================
    max_score += 1
    if momentum_z > 0.3:
        buy_score += 1
        reasons.append(f"Momentum z-score bullish ({momentum_z:.2f})")
    elif momentum_z < -0.3:
        sell_score += 1
        reasons.append(f"Momentum z-score bearish ({momentum_z:.2f})")

    # ================================================================
    # 9. Bollinger Band position  (from adaptive_htf_bias.py)
    # ================================================================
    bb = {"mid": 0.0}
    if _cfg(cfg, "enable_bollinger"):
        max_score += 1
        bb = bollinger_bands(close_s, _cfg(cfg, "bb_length"), _cfg(cfg, "bb_std"))
        last_close = closes[-1]
        if bb["mid"] > 0:
            if last_close > bb["mid"]:
                buy_score += 1
                reasons.append("Price above Bollinger midline")
            else:
                sell_score += 1
                reasons.append("Price below Bollinger midline")

    # ================================================================
    # 10. Noise Filter  (from dual_strategy_with_RSI.py)
    # ================================================================
    noise = spread_noise(highs, lows, closes)
    if _cfg(cfg, "enable_noise_filter"):
        noise_ceil = _cfg(cfg, "noise_ceiling")
        if noise > noise_ceil:
            reasons.append(f"Noise filter active ({noise:.4f} > {noise_ceil}) — dampening signal")
            # Penalize both sides by 1 — too noisy to act confidently
            buy_score = max(0, buy_score - 1)
            sell_score = max(0, sell_score - 1)

    # ================================================================
    # Final direction & score
    # ================================================================
    score = max(buy_score, sell_score)
    min_score = _cfg(cfg, "min_score_for_signal")
    sma_val = sma(close_s, _cfg(cfg, "ma_len"))

    if buy_score >= min_score and buy_score > sell_score:
        direction = "BUY"
    elif sell_score >= min_score and sell_score > buy_score:
        direction = "SELL"
    else:
        direction = "HOLD"

    confidence = score / max_score if max_score > 0 else 0.0

    return SignalResult(
        direction=direction,
        score=score,
        max_score=max_score,
        confidence=confidence,
        reasons=reasons,
        rsi=rsi_val,
        macd_line=m["macd_line"],
        macd_signal=m["signal"],
        macd_histogram=m["histogram"],
        atr_val=atr_val,
        sma_val=sma_val,
        bollinger_mid=bb["mid"],
        spread_noise_val=noise,
        pattern=pattern,
        breakout=breakout,
        divergence=div,
        histogram_expanding=hist_exp,
        momentum_z=momentum_z,
    )
