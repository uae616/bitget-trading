# Next Steps - Dry-Run Testing & Live Trading Plan

## Current Status ✅

**Backtest Complete - Strategy is Viable**

- ✅ XAGUSD (Silver): 47.4% win rate, +4,000 pips profit
- ⚠️ XAUUSD (Gold): 28.1% win rate, not profitable (shelved for now)

**Fixes Applied:**
- ✅ Corrected pip calculation (50 pips now = 5.00 movement)
- ✅ Added signal filtering (trend + cooldown)
- ✅ Switched to M15 timeframe (from M5)
- ✅ Updated config.toml with XAGUSD only

---

## Phase 1: Dry-Run Testing (1-2 weeks)

### What to Do:

**1. Start Dry-Run**
```powershell
cd C:\Users\Administrator\rebalance_bot
python -m src.mt5_scalper.main
```

**Expected Behavior:**
- Logs show: `[DRY] XAGUSD signal=BUY|SELL ...`
- No real trades executed
- P&L is simulated (dry-run)
- Runs continuously until stopped

**2. Monitor Daily**
```powershell
# Check logs (tail last 50 lines)
Get-Content logs/mt5_scalper.log -Tail 50

# Check state.json for P&L
$state = Get-Content state.json -Raw | ConvertFrom-Json
$state.meta | Select-Object cycle, win_rate
```

**3. Track Metrics**
- Win Rate: Should be close to 47.4% (target: 45-50%)
- Total P&L: Should be positive
- Signals per day: Should be 1-3 (not 10+)
- Avg hold time: Should be days, not minutes

**4. Run Time: 1-2 weeks minimum**
- Collect at least 50-100 trades
- Validate win rate holds up
- Test across different market conditions

---

## Phase 2: Go Live (Only if Phase 1 validates)

### Validation Criteria:
✅ Pass ALL of these before going live:

```
Win Rate:     40-55% (backtest: 47.4%)
Total P&L:    Positive
Signals:      1-3 per day (not 20+)
Avg Hold:     Hours to days (not minutes)
Consistency:  Win rate stable across weeks
```

### If You Pass Validation:

**1. Switch to Live Mode**
```toml
# In config.toml, change:
dry_run = false  # ENABLE REAL TRADING

# Keep everything else the same
symbols = ["XAGUSD"]
timeframe = "M15"
position_size = 0.01  # Start micro
```

**2. Start Small (0.01 lots)**
- 0.01 lots = $0.01 per pip
- SL loss = -$0.50 per trade
- TP win = +$1.00 per trade
- Safe if something breaks

**3. Monitor First Week Live**
- Check P&L hourly
- Watch for slippage/spread issues
- Verify order execution
- Monitor account balance

**4. Scale Gradually**
```
Week 1: 0.01 lots (micro)
Week 2-3: 0.02-0.05 lots (small)
Week 4+: 0.1 lots (normal) - only if profitable
```

---

## Phase 3: Troubleshooting

### If Dry-Run Win Rate is Low (<40%):

**Possible Causes:**
1. **Market conditions changed** - Backtest was on old data
   - Solution: Run backtest again on latest data
   
2. **Signal filter too strict** - Missing good trades
   - Solution: Disable cooldown filter (test without it)
   
3. **Spread too wide** - Getting stopped out by noise
   - Solution: Increase SL from 50 to 70 pips

4. **Wrong timeframe** - M15 not working for current market
   - Solution: Try M30 or H1 (even higher)

### If Live Win Rate Diverges from Dry-Run:

**Likely Causes:**
1. **Slippage** - Orders not filling at expected price
   - Check: Spread, liquidity during trade hours
   
2. **Partial fills** - Order only partially executed
   - Check: Position size too large for symbol
   
3. **Spread too wide** - Dry-run assumes tight spread
   - Check: Actual spread vs assumed spread
   
4. **Market hours** - Trading when market is illiquid
   - Check: Trade only during peak hours (14:00-20:00 UTC)

**Solution: Return to dry-run and analyze mismatch**

---

## Important Files

**Configuration:**
- `config.toml` - Trading parameters (already updated)

**Monitoring:**
- `logs/mt5_scalper.log` - Real-time logs
- `state.json` - Current positions and P&L
- `monitor_mt5_live.py` - Dashboard (run in separate window)

**Strategy:**
- `src/mt5_scalper/strategy.py` - Signal logic (has signal filter)
- `src/mt5_scalper/main.py` - Entry/exit logic
- `backtest_mt5.py` - For testing changes

**Documentation:**
- `FIXES_APPLIED_RESULTS.md` - What was fixed and why
- `STRATEGY_IMPROVEMENTS.md` - Failed attempts (reference only)
- `BACKTEST_RESULTS.md` - Original backtest (before fixes)

---

## Quick Reference

### To Start Dry-Run:
```powershell
cd C:\Users\Administrator\rebalance_bot
python -m src.mt5_scalper.main
```

### To Monitor:
```powershell
Get-Content logs/mt5_scalper.log -Tail 50  # Last 50 log lines
```

### To Check P&L:
```powershell
$state = Get-Content state.json -Raw | ConvertFrom-Json
$state.meta  # Shows cycle, win rate, P&L
```

### To Stop Bot:
```powershell
Ctrl+C  # Press in the PowerShell window
```

### To Switch to Live:
```toml
# Edit config.toml:
dry_run = false
position_size = 0.01
```

### To Run Backtest Again:
```powershell
python backtest_mt5.py
```

---

## Checklist Before Going Live

- [ ] Dry-run for 1-2 weeks minimum
- [ ] Win rate is 40-55% (stable)
- [ ] Total P&L is positive
- [ ] Less than 5 signals per day
- [ ] Positions held for hours/days (not minutes)
- [ ] Reviewed logs daily
- [ ] Understand the risk
- [ ] Position size is 0.01 lots (micro)
- [ ] Broker account has at least $500 balance
- [ ] Know how to stop the bot (Ctrl+C)
- [ ] Know how to switch dry_run=true if something breaks

---

## Risk Management

### Daily Loss Limit:
- If daily loss > $50, STOP trading
- Review what went wrong
- Don't revenge trade

### Weekly Review:
- Check win rate vs backtest
- Check total P&L
- Are spreads wider than expected?
- Are orders filling at expected prices?

### Monthly Scaling:
- Only increase lot size if:
  - 4 weeks of consistent profit
  - Win rate >45%
  - Daily loss limit never hit
  - Trades executing as expected

### Emergency Kill Switch:
- If live trading breaks:
  1. Set `dry_run = true` in config.toml
  2. Restart the bot
  3. All subsequent trades will be simulated
  4. No real money at risk
  5. Debug the issue

---

## Expected Monthly Profit (at 47.4% win rate)

### At 0.01 lots:
- Per trade profit: 47.4% × (+$1.00) - 52.6% × (-$0.50) = **+$0.21**
- If 30 trades/month: **+$6.30/month**
- If 100 trades/month: **+$21/month**
- Small but POSITIVE and SAFE

### At 0.05 lots (after 4 weeks profit):
- Per trade profit: **+$1.05**
- If 30 trades/month: **+$31.50/month**
- If 100 trades/month: **+$105/month**

### At 0.1 lots (after 2+ months profit):
- Per trade profit: **+$2.10**
- If 30 trades/month: **+$63/month**
- If 100 trades/month: **+$210/month**

---

## Summary

1. **Backtest Done** ✅ - XAGUSD viable (47.4% WR, +4000 pips)
2. **Dry-Run Next** - Run for 1-2 weeks to validate
3. **Go Live** - Only if dry-run matches backtest
4. **Start Small** - 0.01 lots first
5. **Scale Slowly** - Increase only after consistent profit

**Good luck! 🚀**
