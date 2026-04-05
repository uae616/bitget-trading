# MT5 SCALPER: DRY RUN → LIVE TRADING GUIDE

## ✅ Pre-Flight Checklist

### 1. Verify MT5 Setup
- [ ] MetaTrader5 terminal is running and connected
- [ ] Account is logged in (check top of terminal window)
- [ ] Check "Experts Advisors" are enabled (Tools → Options → Expert Advisors)
- [ ] Demo or real account is selected (verify account number)

### 2. Verify Bot Configuration
Check `config.toml`:
```
[mt5_scalper]
dry_run = false              # ← CHANGE THIS TO START LIVE
symbols = ["XAUUSD", "XAGUSD"]
timeframe = "M5"
cycle_seconds = 60
bars = 200
```

Check `.env` for credentials:
```
MT5_LOGIN=your_account_number
MT5_PASSWORD=your_password
MT5_SERVER=broker_server_name
```

### 3. Risk Management Setup
- [ ] Position size set to MICRO lots (0.01 to start)
- [ ] Stop-loss configured (check `src/mt5_scalper/execution.py`)
- [ ] Take-profit configured
- [ ] Daily loss limit set in config
- [ ] Maximum open positions limited (default: 2)

### 4. Account Verification
- [ ] Account type: Demo or Live? (recommend starting on Demo)
- [ ] Available margin sufficient for position size
- [ ] No pending orders or positions from previous runs

---

## 🚀 Safe Transition Steps

### Phase 1: DEMO ACCOUNT (0-2 hours)
1. Start with small position sizes (0.01 lots = $1 per pip)
2. Run with monitoring active: `python monitor_mt5_live.py`
3. Watch for:
   - Signals being generated every 5 minutes
   - Positions opening and closing correctly
   - P&L calculations accurate
   - No MT5 connection errors in logs

### Phase 2: TINY LIVE ACCOUNT (2-8 hours)
1. Switch to real account with micro position size (0.01 lots)
2. Limit to 1-2 open positions maximum
3. Monitor every 15 minutes
4. Watch for:
   - Real slippage vs simulated slippage
   - Order fills are happening
   - No unexpected errors with live data

### Phase 3: NORMAL LIVE (8+ hours)
1. Increase position size gradually (0.02, 0.05, 0.1 lots)
2. Expand to 3-4 open positions if performing well
3. Monitor hourly
4. Adjust risk parameters based on live performance

---

## 📊 Using the Monitoring Dashboard

### Start Monitoring
```powershell
# Monitor with 10-second refresh (default)
python monitor_mt5_live.py

# Monitor with custom refresh interval
python monitor_mt5_live.py 5
```

### Key Metrics to Watch
- **Win Rate**: Should be >40% for profitability (scalping typically 45-55%)
- **P&L**: Should trend positive or stay near break-even
- **Signal Distribution**: BUY/SELL should be balanced (40-60% split)
- **Closed Trades**: Track how many trades complete per hour
- **Open Positions**: Should not exceed configured maximum

### Red Flags 🚨
- P&L consistently negative → STOP immediately
- Win rate drops below 30% → Strategy not working
- Signals all BUY or all SELL → Signal drift detected
- Positions not closing → Execution issue with MT5
- Connection errors in logs → MT5 terminal disconnected

---

## 📋 Step-by-Step Activation

### Step 1: Backup Current Config
```powershell
Copy-Item config.toml config.toml.backup
Copy-Item .env .env.backup
```

### Step 2: Update Config (DEMO FIRST)
```toml
[mt5_scalper]
dry_run = false              # Enable live trading
symbols = ["XAUUSD", "XAGUSD"]
timeframe = "M5"
cycle_seconds = 60           # One signal every minute
bars = 200

# Risk settings
position_size = 0.01         # Micro lot size
max_positions = 2            # Max 2 open trades
stop_loss_pips = 20          # 20 pips SL
take_profit_pips = 40        # 40 pips TP
```

### Step 3: Verify .env Credentials
```
MT5_LOGIN=your_demo_account_number
MT5_PASSWORD=your_password
MT5_SERVER=correct_server_name
```
Get the exact server name from MT5: Tools → Options → Accounts tab

### Step 4: Start Bot in Terminal 1
```powershell
python -m src.mt5_scalper.main
```

### Step 5: Start Monitoring in Terminal 2
```powershell
python monitor_mt5_live.py 10
```

### Step 6: Watch for First Signal (30-60 seconds)
- Bot should log "[DRY] ..." messages (when dry_run=true) or "[LIVE] ..." (when false)
- Check dashboard shows signal generation
- Monitor logs/mt5_scalper.log for errors

---

## 🛑 Emergency Stop

If something goes wrong:

```powershell
# 1. Immediately stop the bot (Ctrl+C in the terminal)

# 2. Manually close any open positions in MT5:
#    - Right-click position → Close Position
#    - Or: Tools → History to verify order execution

# 3. Revert to dry_run = true
Set-Content config.toml (Get-Content config.toml) -Replace "dry_run = false", "dry_run = true"

# 4. Check logs for errors
tail -f logs/mt5_scalper.log
```

---

## 📝 Transition Timeline Recommendations

| Timeline | Account Type | Position Size | Max Trades | Action |
|----------|-------------|---------------|-----------|---------|
| 0-1 hour | Demo | 0.01 | 1 | Verify signals & execution |
| 1-2 hours | Demo | 0.02 | 2 | Monitor performance |
| 2-4 hours | Live (micro) | 0.01 | 2 | Real money, low risk |
| 4-8 hours | Live (micro) | 0.02 | 3 | Scale if profitable |
| 8+ hours | Live (micro) | 0.05 | 4 | Full micro position |

---

## 🔍 What to Monitor in Logs

```
✅ Good Signs:
[INFO] [LIVE] XAUUSD signal=BUY score=1 conf=0.52
[INFO] ENTRY_BUY XAUUSD 2325.50
[INFO] EXIT_SELL XAUUSD 2325.70 pnl=+20.0
[HEARTBEAT] cycle=XX symbols=2

❌ Bad Signs:
[ERROR] MT5 connection lost
[ERROR] Failed to open order
[WARN] Order timeout
Connection refused
```

---

## 💡 Pro Tips

1. **First Trade**: Don't expect perfect results. First 5-10 trades are for calibration.

2. **Slippage**: Live trading has slippage that wasn't in dry run. Allow 1-2 pips margin.

3. **Spread**: Check bid-ask spread during your trading hours. Wide spread = harder fills.

4. **Time Zone**: Make sure MT5 server time matches your config expectations.

5. **Logs**: Always keep logs open. `monitor_mt5_live.py` is just a dashboard; logs show the truth.

6. **Gradual Scale**: Never jump from 0.01 to 1.0 lot size. Scale gradually.

7. **24/7 Monitor**: First 8 hours of live trading should have constant monitoring.

---

## 📞 If Something Goes Wrong

1. Check logs: `tail -f logs/mt5_scalper.log`
2. Verify MT5 is connected: Open MT5 → check Connection indicator
3. Check network: Ping google.com (verify internet connection)
4. Restart MT5 if connection lost
5. Increase `cycle_seconds` if bot is falling behind
6. Revert to `dry_run = true` and investigate

---

## Next Steps

1. ✅ Verify checklist items above
2. ✅ Backup your config
3. ✅ Update config.toml for DEMO account
4. ✅ Run `python monitor_mt5_live.py` in one terminal
5. ✅ Run `python -m src.mt5_scalper.main` in another terminal
6. ✅ Watch first 30 minutes closely
7. ✅ Review log file for any errors
8. ✅ Once confident on DEMO, switch to LIVE with 0.01 size

Good luck! 🚀
