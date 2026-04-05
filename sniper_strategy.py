"""
Sniper Entry/Exit with SL & TP by KhanSaab V.02
Python conversion of the Pine Script indicator.

Requirements:
    pip install ccxt pandas pandas-ta

Usage:
    python sniper_strategy.py
    python sniper_strategy.py --symbol ETH/USDT --interval 4h --limit 300
"""

import argparse
import sys

try:
    import ccxt
    import pandas as pd
    import pandas_ta as ta
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install with: pip install ccxt pandas pandas-ta")
    sys.exit(1)


# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
ATR_MULTIPLIER = 1.5   # SL ATR Multiplier — increase for wider stops, decrease for tighter
EMA_FAST       = 9     # Fast EMA period
EMA_SLOW       = 21    # Slow EMA period
RSI_PERIOD     = 14
ATR_PERIOD     = 14
ADX_PERIOD     = 14
MACD_FAST      = 12
MACD_SLOW      = 26
MACD_SIGNAL    = 9
VOL_AVG_PERIOD = 20


# ─────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────
def fetch_ohlcv(symbol: str, interval: str = "1h", limit: int = 200) -> pd.DataFrame:
    """
    Fetch OHLCV data from Binance. Falls back to KuCoin if Binance fails.
    You can swap exchange = ccxt.bybit() / ccxt.okx() / etc. as needed.
    """
    exchanges_to_try = [
        ccxt.binance({"enableRateLimit": True}),
        ccxt.kucoin({"enableRateLimit": True}),
    ]

    for exchange in exchanges_to_try:
        try:
            print(f"Fetching {symbol} [{interval}] from {exchange.id}...")
            raw = exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            return df
        except Exception as e:
            print(f"  {exchange.id} failed: {e}")

    raise RuntimeError(f"Could not fetch data for {symbol} from any exchange.")


# ─────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all indicators used by the Sniper strategy.
    Mirrors the Pine Script indicator block exactly.
    """
    df = df.copy()

    # EMAs
    df["ema9"]  = ta.ema(df["close"], length=EMA_FAST)
    df["ema21"] = ta.ema(df["close"], length=EMA_SLOW)

    # VWAP (cumulative, resets each session — Pine Script default)
    df["hlc3"] = (df["high"] + df["low"] + df["close"]) / 3
    df["vwap"] = (df["hlc3"] * df["volume"]).cumsum() / df["volume"].cumsum()

    # RSI
    df["rsi"] = ta.rsi(df["close"], length=RSI_PERIOD)

    # MACD
    macd_df = ta.macd(df["close"], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
    df["macd"]        = macd_df[f"MACD_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"]
    df["macd_signal"] = macd_df[f"MACDs_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"]

    # ATR
    df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=ATR_PERIOD)

    # ADX
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=ADX_PERIOD)
    df["adx"] = adx_df[f"ADX_{ADX_PERIOD}"]

    # Volume average
    df["vol_avg"] = df["volume"].rolling(VOL_AVG_PERIOD).mean()

    return df


# ─────────────────────────────────────────
# SIGNAL LOGIC
# ─────────────────────────────────────────
def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect EMA crossover/crossunder signals and compute trade setups.
    Mirrors the Pine Script signal logic block.
    """
    df = df.copy()
    df["signal"]    = None    # "BUY" or "SELL"
    df["is_retest"] = False

    # Trade setup columns
    for col in ["entry", "sl", "tp1", "tp2", "tp3", "tp4", "tp5",
                "tp1_hit", "tp2_hit", "tp3_hit", "tp4_hit", "tp5_hit"]:
        df[col] = None

    last_state = 0   # 0 = neutral, 1 = long, -1 = short
    entry = sl = t1 = t2 = t3 = t4 = t5 = 0.0
    t1h = t2h = t3h = t4h = t5h = False

    for i in range(1, len(df)):
        row  = df.iloc[i]
        prev = df.iloc[i - 1]

        e9  = row["ema9"]
        e21 = row["ema21"]
        pe9  = prev["ema9"]
        pe21 = prev["ema21"]

        if pd.isna(e9) or pd.isna(e21) or pd.isna(pe9) or pd.isna(pe21):
            continue

        # EMA crossover / crossunder
        crossover  = (pe9 <= pe21) and (e9 > e21)
        crossunder = (pe9 >= pe21) and (e9 < e21)

        trigger_buy  = crossover  and last_state <= 0
        trigger_sell = crossunder and last_state >= 0

        if trigger_buy or trigger_sell:
            last_state = 1 if trigger_buy else -1
            entry = row["close"]
            risk  = (row["atr"] or 0.01) * ATR_MULTIPLIER

            sl = entry - risk if trigger_buy else entry + risk
            t1 = entry + risk        if trigger_buy else entry - risk
            t2 = entry + risk * 2   if trigger_buy else entry - risk * 2
            t3 = entry + risk * 3   if trigger_buy else entry - risk * 3
            t4 = entry + risk * 4   if trigger_buy else entry - risk * 4
            t5 = entry + risk * 5   if trigger_buy else entry - risk * 5
            t1h = t2h = t3h = t4h = t5h = False

            df.iloc[i, df.columns.get_loc("signal")] = "BUY" if trigger_buy else "SELL"
            for col, val in [("entry", entry), ("sl", sl),
                             ("tp1", t1), ("tp2", t2), ("tp3", t3),
                             ("tp4", t4), ("tp5", t5)]:
                df.iloc[i, df.columns.get_loc(col)] = val

        # Target hit detection
        if last_state == 1:
            if row["high"] >= t1: t1h = True
            if row["high"] >= t2: t2h = True
            if row["high"] >= t3: t3h = True
            if row["high"] >= t4: t4h = True
            if row["high"] >= t5: t5h = True
        elif last_state == -1:
            if row["low"] <= t1: t1h = True
            if row["low"] <= t2: t2h = True
            if row["low"] <= t3: t3h = True
            if row["low"] <= t4: t4h = True
            if row["low"] <= t5: t5h = True

        # Retest detection (orange candle in Pine Script)
        is_retest = (
            (last_state == 1  and row["low"] <= e9 and row["low"] > e21) or
            (last_state == -1 and row["high"] >= e9 and row["high"] < e21)
        )
        df.iloc[i, df.columns.get_loc("is_retest")] = is_retest
        df.iloc[i, df.columns.get_loc("tp1_hit")]   = t1h
        df.iloc[i, df.columns.get_loc("tp2_hit")]   = t2h
        df.iloc[i, df.columns.get_loc("tp3_hit")]   = t3h
        df.iloc[i, df.columns.get_loc("tp4_hit")]   = t4h
        df.iloc[i, df.columns.get_loc("tp5_hit")]   = t5h

    return df


# ─────────────────────────────────────────
# DASHBOARD (BULL/BEAR SCORE)
# ─────────────────────────────────────────
def compute_dashboard(df: pd.DataFrame) -> dict:
    """
    Compute the dual bull/bear score and market bias from the last bar.
    Mirrors the Pine Script dashboard logic.
    """
    row = df.iloc[-1]

    close    = row["close"]
    vwap     = row["vwap"]
    rsi      = row["rsi"]
    macd     = row["macd"]
    macd_sig = row["macd_signal"]
    ema9     = row["ema9"]
    ema21    = row["ema21"]
    adx      = row["adx"]
    volume   = row["volume"]
    vol_avg  = row["vol_avg"]
    open_    = row["open"]

    # Bull conditions
    bull_conditions = [
        close > vwap,
        rsi > 50,
        macd > macd_sig,
        ema9 > ema21,
        adx > 25 and close > ema9,
        volume > vol_avg and close > open_,
    ]

    # Bear conditions
    bear_conditions = [
        close < vwap,
        rsi < 50,
        macd < macd_sig,
        ema9 < ema21,
        adx > 25 and close < ema9,
        volume > vol_avg and close < open_,
    ]

    b_score = sum(bull_conditions)
    r_score = sum(bear_conditions)
    bull_pct = round((b_score / len(bull_conditions)) * 100)
    bear_pct = round((r_score / len(bear_conditions)) * 100)

    diff = bull_pct - bear_pct
    if diff >= 40:
        bias = "STRONG BULL"
    elif diff <= -40:
        bias = "STRONG BEAR"
    elif diff > 0:
        bias = "MILD BULL"
    else:
        bias = "MILD BEAR"

    return {
        "bull_score": bull_pct,
        "bear_score": bear_pct,
        "bias": bias,
        "price_vs_vwap": "ABOVE" if close > vwap else "BELOW",
        "rsi": round(rsi, 1) if not pd.isna(rsi) else 0,
        "macd_trend": "BULL" if macd > macd_sig else "BEAR",
        "adx": round(adx, 1) if not pd.isna(adx) else 0,
        "ema_cross": "BULL" if ema9 > ema21 else "BEAR",
        "atr": round(row["atr"], 4) if not pd.isna(row["atr"]) else 0,
        "vol_status": "HIGH" if volume > vol_avg else "LOW",
        "trend_strength": "STRONG" if adx > 25 else "WEAK",
        "macd_main": round(macd, 4) if not pd.isna(macd) else 0,
        "macd_signal_val": round(macd_sig, 4) if not pd.isna(macd_sig) else 0,
    }


# ─────────────────────────────────────────
# DISPLAY
# ─────────────────────────────────────────
def print_dashboard(dashboard: dict, symbol: str, interval: str) -> None:
    sep = "─" * 42
    print(f"\n{sep}")
    print(f"  SNIPER TERMINAL — {symbol} [{interval}]")
    print(sep)
    print(f"  {'BULL SCORE':<20} {dashboard['bull_score']}%")
    print(f"  {'BEAR SCORE':<20} {dashboard['bear_score']}%")
    print(f"  {'MARKET BIAS':<20} {dashboard['bias']}")
    print(sep)
    print(f"  {'Price/VWAP':<20} {dashboard['price_vs_vwap']}")
    print(f"  {'RSI (14)':<20} {dashboard['rsi']}")
    print(f"  {'MACD Trend':<20} {dashboard['macd_trend']}")
    print(f"  {'ADX Power':<20} {dashboard['adx']}")
    print(f"  {'EMA Cross':<20} {dashboard['ema_cross']}")
    print(f"  {'ATR 14':<20} {dashboard['atr']}")
    print(f"  {'Vol Status':<20} {dashboard['vol_status']}")
    print(f"  {'Trend Strength':<20} {dashboard['trend_strength']}")
    print(f"  {'MACD Main':<20} {dashboard['macd_main']}")
    print(f"  {'MACD Signal':<20} {dashboard['macd_signal_val']}")
    print(sep)


def print_trade_setup(df: pd.DataFrame) -> None:
    # Find the most recent signal
    signal_rows = df[df["signal"].notna()]
    if signal_rows.empty:
        print("  No active trade setup found.")
        return

    last_signal = signal_rows.iloc[-1]
    signal_time = last_signal.name
    direction   = last_signal["signal"]
    entry  = last_signal["entry"]
    sl     = last_signal["sl"]
    tp1    = last_signal["tp1"]
    tp2    = last_signal["tp2"]
    tp3    = last_signal["tp3"]
    tp4    = last_signal["tp4"]
    tp5    = last_signal["tp5"]

    # Check which TPs have been hit since signal bar
    since_signal = df.loc[signal_time:]
    tp1_hit = tp2_hit = tp3_hit = tp4_hit = tp5_hit = False
    for _, r in since_signal.iterrows():
        if direction == "BUY":
            if r["high"] >= tp1: tp1_hit = True
            if r["high"] >= tp2: tp2_hit = True
            if r["high"] >= tp3: tp3_hit = True
            if r["high"] >= tp4: tp4_hit = True
            if r["high"] >= tp5: tp5_hit = True
        else:
            if r["low"] <= tp1: tp1_hit = True
            if r["low"] <= tp2: tp2_hit = True
            if r["low"] <= tp3: tp3_hit = True
            if r["low"] <= tp4: tp4_hit = True
            if r["low"] <= tp5: tp5_hit = True

    def fmt(price, hit): return f"{price:.4f}" + (" 🔥" if hit else "")

    sep = "─" * 42
    print(f"\n  ACTIVE TRADE SETUP  [{direction}] @ {signal_time}")
    print(sep)
    print(f"  {'ENTRY':<20} {entry:.4f}")
    print(f"  {'STOP LOSS':<20} {sl:.4f}")
    print(f"  {'TP1':<20} {fmt(tp1, tp1_hit)}")
    print(f"  {'TP2':<20} {fmt(tp2, tp2_hit)}")
    print(f"  {'TP3':<20} {fmt(tp3, tp3_hit)}")
    print(f"  {'TP4':<20} {fmt(tp4, tp4_hit)}")
    print(f"  {'TP5':<20} {fmt(tp5, tp5_hit)}")
    print(sep)


def print_recent_signals(df: pd.DataFrame, n: int = 5) -> None:
    signals = df[df["signal"].notna()].tail(n)
    if signals.empty:
        print("  No signals found in this data range.")
        return

    print(f"\n  LAST {len(signals)} SIGNALS")
    print("─" * 42)
    print(f"  {'Time':<22} {'Signal':<8} {'Entry'}")
    print("─" * 42)
    for ts, row in signals.iterrows():
        print(f"  {str(ts):<22} {row['signal']:<8} {row['entry']:.4f}")
    print("─" * 42)


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def run(symbol: str = "BTC/USDT", interval: str = "1h", limit: int = 200) -> pd.DataFrame:
    df = fetch_ohlcv(symbol, interval, limit)
    df = compute_indicators(df)
    df = compute_signals(df)
    dashboard = compute_dashboard(df)

    print_dashboard(dashboard, symbol, interval)
    print_trade_setup(df)
    print_recent_signals(df)

    return df   # Return df so you can do further analysis in a notebook or script


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sniper Entry/Exit by KhanSaab — Python Edition")
    parser.add_argument("--symbol",   default="BTC/USDT", help="Trading pair, e.g. ETH/USDT")
    parser.add_argument("--interval", default="1h",       help="Timeframe: 1m 5m 15m 1h 4h 1d")
    parser.add_argument("--limit",    default=200, type=int, help="Number of candles to fetch")
    args = parser.parse_args()

    run(symbol=args.symbol, interval=args.interval, limit=args.limit)
