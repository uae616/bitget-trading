# BACKTEST RESULTS - CRITICAL ANALYSIS

## Summary

Your MT5 Scalper strategy has been backtested on **5,000 bars of historical data** (approximately 17 days).

**RESULT: ❌ NOT PROFITABLE - DO NOT TRADE LIVE**

---

## Detailed Results

### XAUUSD (Gold)
```
Trades Executed:    2,400
Win Rate:           5.0% (121 wins, 2,279 losses)
Total P&L:          -40,740 pips
Avg P&L per Trade:  -16.97 pips
```

**Verdict: 🚨 COMPLETE FAILURE**
- Losing on 95% of trades
- Only 5% win rate is catastrophically bad
- Loses 16-17 pips per trade on average
- Strategy is fundamentally wrong for XAUUSD

### XAGUSD (Silver)
```
Trades Executed:    1,171
Win Rate:           33.4% (391 wins, 780 losses)
Total P&L:          +40 pips (barely break even)
Avg P&L per Trade:  +0.03 pips
```

**Verdict: ⚠️ MARGINALLY VIABLE BUT NOT TRADEABLE**
- 33% win rate is too low
- Only +40 pips profit on 1,171 trades
- Average profit is essentially 0
- Not enough margin of safety

### Combined Results
```
Total Trades:       3,571
Total Win Rate:     14.3% (512 wins)
Total P&L:          -40,700 pips
```

**Verdict: ❌ LOSING STRATEGY**
- Average loss per trade
- Strategy loses money overall

---

## What This Means in Real Money

If you traded with this strategy at different position sizes:

| Position Size | Per Pip Value | Total Loss per Cycle |
|---|---|---|
| 0.01 lots | $1 | -$40,700 |
| 0.1 lots | $10 | -$407,000 |
| 1.0 lot | $100 | -$4,070,000 |

**You would LOSE MASSIVE amounts of money trading live.**

---

## Why the Strategy is Failing

### 1. Signal Logic is Too Simple
The current strategy uses:
```python
fast = sum(closes[-9:]) / 9.0      # Last 9 closes (9-period SMA)
slow = sum(closes[-21:]) / 21.0    # Last 21 closes (21-period SMA)

if fast > slow: BUY
if fast < slow: SELL
```

**Problems:**
- Simple moving average crossover is a basic strategy
- Works only in strong trending markets
- Fails in sideways/choppy markets
- Too many false signals (2,400 on XAUUSD!)
- Signal appears every bar, not just on real setups

### 2. Stop-Loss is Too Tight
Current: 20 pips SL

**Problems:**
- 95% of trades hit the 20-pip SL on XAUUSD
- This means the entries are BAD
- Strategy opens positions at wrong times
- Gets immediately stopped out

### 3. Entry Points are Wrong
The strategy generates signals whenever fast > slow or fast < slow, which happens too frequently:
- 2,400 signals on 5,000 bars of XAUUSD
- That's a signal every 2 bars!
- Most are false signals

---

## Specific Issues

### XAUUSD Issue
- Only 5% winning trades
- The signal logic doesn't work for gold
- Possibly because:
  - Gold is highly volatile
  - EMA crossover doesn't capture volatility well
  - Need different parameters or indicators

### XAGUSD Issue
- Better than gold (33% vs 5%)
- But still not profitable
- +40 pips on 1,171 trades is not enough

### General Problem
The strategy needs:
1. **Better signal filtering** - Reduce false positives
2. **Better entry logic** - Not just simple EMA crossover
3. **Better risk parameters** - Adjust SL/TP
4. **Additional filters** - Add confirmation indicators

---

## How to Run Backtest Again

After making improvements to the strategy:

```powershell
python backtest_mt5.py
```

This will:
1. Fetch 5,000 bars of historical data from MT5
2. Simulate the strategy on all bars
3. Calculate win rate and P&L
4. Show if you're profitable

---

## What Needs to Happen Next

### Option 1: Improve the Strategy (RECOMMENDED)
1. **Review src/mt5_scalper/strategy.py**
   - Current: Basic EMA crossover
   - Needed: More sophisticated logic

2. **Improve the signal logic:**
   - Use different EMA periods (e.g., 7/14 instead of 9/21)
   - Add additional indicators (RSI, MACD, Stochastic)
   - Add filters to reduce false signals
   - Consider volume analysis

3. **Optimize stop-loss/take-profit:**
   - Increase SL from 20 to 40-50 pips
   - Adjust TP accordingly (maybe 80-100 pips)
   - Use ATR (Average True Range) based stops

4. **Test on different timeframes:**
   - Current: M5 (5-minute candles)
   - Try M15 or M30 for longer-term trades

5. **Re-run backtest:**
   ```powershell
   python backtest_mt5.py
   ```
   - Goal: Win rate >50%
   - Goal: Positive total P&L

### Option 2: Use Proven Strategy
- The EMA crossover is too basic for scalping
- Look for a proven MT5 scalping strategy
- Test it with backtest_mt5.py first

### Option 3: Switch Instruments
- Maybe XAUUSD/XAGUSD are too difficult
- Try currency pairs (EURUSD, GBPUSD, etc.)
- Test with backtest_mt5.py

---

## Example Improvement

Here's what a better strategy might look like:

```python
# Improved strategy with filters
def compute_signal_improved(ohlcv, symbol):
    closes = [float(c[4]) for c in ohlcv]
    
    # Multiple EMAs
    ema7 = sum(closes[-7:]) / 7.0
    ema14 = sum(closes[-14:]) / 14.0
    ema21 = sum(closes[-21:]) / 21.0
    
    # RSI filter (avoid overbought/oversold)
    rsi = calculate_rsi(closes)
    
    # Only take signals if:
    # 1. EMA crossover occurs
    # 2. RSI is not at extremes (not >70 or <30)
    # 3. Price is above/below key levels
    
    if ema7 > ema14 > ema21 and rsi < 70:
        return Signal(direction="BUY", ...)
    elif ema7 < ema14 < ema21 and rsi > 30:
        return Signal(direction="SELL", ...)
    else:
        return Signal(direction="HOLD", ...)
```

---

## Current State

| Aspect | Status |
|--------|--------|
| Signal Generation | ✅ Working |
| Entry Logic | ✅ Working (but generating wrong signals) |
| Exit Logic | ✅ Working |
| P&L Calculation | ✅ Working |
| **Profitability** | ❌ **NOT PROFITABLE** |
| **Ready for Live?** | ❌ **NO** |

---

## Summary

```
┌─────────────────────────────────────────────┐
│ XAUUSD: 5% win rate - LOSING ❌            │
│ XAGUSD: 33% win rate - NOT PROFITABLE ⚠️  │
│ Overall: 14% win rate - LOSING ❌          │
│                                             │
│ ❌ DO NOT TRADE LIVE                       │
│ ✅ FIX STRATEGY FIRST                      │
│ ✅ RE-RUN BACKTEST AFTER CHANGES           │
│ ✅ ONLY GO LIVE WHEN WIN RATE >45%         │
└─────────────────────────────────────────────┘
```

---

## Files

- **backtest_mt5.py** - Run backtests on your strategy
- **src/mt5_scalper/strategy.py** - Improve the signal logic here
- **PNL_CALCULATION_FIX.md** - How P&L is calculated

---

## Next Action

🚨 **DO NOT GO LIVE**

Instead:
1. Review and improve src/mt5_scalper/strategy.py
2. Run `python backtest_mt5.py` to test changes
3. Keep improving until win rate > 45%
4. Only then consider going live with micro position size

Good luck! 💪
