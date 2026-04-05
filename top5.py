import pandas as pd
import pandas_ta as ta
import numpy as np
import yfinance as yf # Or use CCXT for crypto

# 1. THE CORE LOGIC (Unified Functions)
def get_unified_signals(df, ticker):
    # --- BigBeluga: Swing Structure ---
    swing_len = 20
    df['hh'] = df['high'] == df['high'].rolling(swing_len*2+1, center=True).max()
    df['ll'] = df['low'] == df['low'].rolling(swing_len*2+1, center=True).min()
    
    # --- KhanSaab: Multi-Factor Indicators ---
    ema9 = ta.ema(df['close'], length=9)
    ema21 = ta.ema(df['close'], length=21)
    rsi = ta.rsi(df['close'], length=14)
    macd = ta.macd(df['close'])
    adx = ta.adx(df['high'], df['low'], df['close'])
    vwap = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
    
    # --- GainzAlgo: Logistic Momentum ---
    def logistic_prob(series, slope=0.15):
        mean = series.rolling(100).mean()
        z = (series - mean) * slope
        return 1 / (1 + np.exp(-z))
    
    prob_plus = logistic_prob(adx['DMP_14'])
    prob_minus = logistic_prob(adx['DMN_14'])
    momentum = np.tanh((prob_plus - prob_minus) * 2.0)
    
    # 2. THE SCORING ENGINE (Exact same weights as Pine)
    score = 0
    score += (rsi.iloc[-1] > 50)
    score += (macd['MACD_12_26_9'].iloc[-1] > macd['MACDs_12_26_9'].iloc[-1])
    score += (ema9.iloc[-1] > ema21.iloc[-1])
    score += (adx['ADX_14'].iloc[-1] > 25 and adx['DMP_14'].iloc[-1] > adx['DMN_14'].iloc[-1])
    score += (df['close'].iloc[-1] > vwap.iloc[-1])
    
    score_pct = (score / 5) * 100
    
    # 3. SIGNAL GENERATION
    status = "NEUTRAL"
    if score_pct >= 80 and momentum.iloc[-1] > 0.5:
        status = "STRONG BUY ðŸ”¥"
    elif score_pct <= 20 and momentum.iloc[-1] < -0.5:
        status = "STRONG SELL â„ï¸"
        
    return {
        "Ticker": ticker,
        "Score": f"{score_pct}%",
        "Momentum": round(momentum.iloc[-1], 2),
        "Trend": "UP" if ema9.iloc[-1] > ema21.iloc[-1] else "DOWN",
        "Signal": status
    }

# 4. THE SCANNER LOOP
tickers = ["AAPL", "TSLA", "BTC-USD", "ETH-USD", "NVDA", "AMD"]
scanner_results = []

print("Scanning markets...")
for symbol in tickers:
    try:
        # Fetching last 200 bars (Daily timeframe)
        data = yf.download(symbol, period="1y", interval="1d", progress=False)
        if not data.empty:
            result = get_unified_signals(data, symbol)
            scanner_results.append(result)
    except Exception as e:
        print(f"Error scanning {symbol}: {e}")

# 5. DISPLAY RESULTS
scan_df = pd.DataFrame(scanner_results)
print("\n--- SCANNER RESULTS ---")
print(scan_df.to_string(index=False))