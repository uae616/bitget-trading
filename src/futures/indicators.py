from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, length: int) -> float:
    if series is None or len(series) < max(1, length):
        return 0.0
    return float(series.rolling(length).mean().iloc[-1])


def rsi(series: pd.Series, length: int = 14) -> float:
    if series is None or len(series) < length + 1:
        return 50.0
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(length).mean()
    avg_loss = loss.rolling(length).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    value = 100 - (100 / (1 + rs))
    latest = value.iloc[-1]
    if pd.isna(latest):
        return 50.0
    return float(latest)
