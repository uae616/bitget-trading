# 🚀 MT5 SCALPER LIVE TRADING - QUICK START

Your dry run is **successful**! Here's what you have:

## 📊 What We Created

### 1. **Monitoring Dashboard** (`monitor_mt5_live.py`)
   - Real-time P&L tracking
   - Win rate calculation
   - Signal statistics
   - Open positions display
   - Auto-refresh every 10 seconds

   **Usage:**
   ```powershell
   python monitor_mt5_live.py          # Default 10s refresh
   python monitor_mt5_live.py 5        # 5s refresh for intense monitoring
   ```

### 2. **Transition Guide** (`MT5_TRANSITION_GUIDE.md`)
   - Complete checklist for going live
   - Risk management setup
   - Safe transition phases
   - Emergency stop procedures
   - Red flags to watch

### 3. **Transition Script** (`scripts/transition_mt5.ps1`)
   - Automated config management
   - Backup your settings
   - Safe mode switching
   - MT5 connection testing

   **Usage:**
   ```powershell
   # Check everything
   .\scripts\transition_mt5.ps1 -Mode check

   # Switch to demo (still dry_run, but with position size settings)
   .\scripts\transition_mt5.ps1 -Mode demo

   # Switch to live micro (0.01 lots)
   .\scripts\transition_mt5.ps1 -Mode live-micro

   # Switch to live small (0.05 lots)
   .\scripts\transition_mt5.ps1 -Mode live-small

   # Revert to dry_run
   .\scripts\transition_mt5.ps1 -Mode revert
   ```

---

## ⚡ REQUIRED SETUP BEFORE GOING LIVE

### Step 1: Add MT5 Credentials to `.env`

Open `.env` and add these lines:
```
# MetaTrader5 credentials
MT5_LOGIN=your_account_number
MT5_PASSWORD=your_password
MT5_SERVER=your_broker_server_name
```

**How to find these:**
1. Open MetaTrader5
2. File → Account Settings (or press F11)
3. Find your Login Number (account number)
4. Find your Server Name (e.g., "ICmarkets-Live" or "FinPro-Demo")
5. You already know your password

**Example:**
```
MT5_LOGIN=123456789
MT5_PASSWORD=MySecurePass123
MT5_SERVER=FinPro-Demo
```

### Step 2: Verify Configuration

Run the transition script:
```powershell
cd C:\Users\Administrator\rebalance_bot
.\scripts\transition_mt5.ps1 -Mode check
```

This will verify:
- ✅ All required files exist
- ✅ Credentials are in `.env`
- ✅ MT5 terminal can be connected
- ✅ Your config is valid

### Step 3: Start with Demo Account

```powershell
# Terminal 1: Run the bot
python -m src.mt5_scalper.main

# Terminal 2 (in same directory): Monitor it
python monitor_mt5_live.py
```

Watch the monitor dashboard. You should see:
- Signals being generated every 5 minutes
- P&L updates as trades open/close
- Win rate calculation
- No errors in logs

---

## 🎯 Three-Phase Transition Plan

### Phase 1: DEMO (Dry Run) - 1-2 hours
```powershell
# Check everything is working
.\scripts\transition_mt5.ps1 -Mode check

# Switch to demo mode (optional, just confirms settings)
.\scripts\transition_mt5.ps1 -Mode demo

# Run the bot
python -m src.mt5_scalper.main
python monitor_mt5_live.py
```

**Goals:**
- ✅ Signals are being generated consistently
- ✅ Strategy shows expected pattern
- ✅ No MT5 connection errors

---

### Phase 2: LIVE MICRO (0.01 lots) - Next 2-8 hours
```powershell
# THIS USES REAL MONEY - Small position size
.\scripts\transition_mt5.ps1 -Mode live-micro

# Start bot and monitor
python -m src.mt5_scalper.main
python monitor_mt5_live.py
```

**Watch for:**
- Real trades opening and closing
- Order fills are happening
- Slippage vs expected entry/exit
- P&L is realistic

---

### Phase 3: LIVE SMALL (0.05 lots) - Once confident
```powershell
# Scale up position size
.\scripts\transition_mt5.ps1 -Mode live-small

# Continue monitoring
python -m src.mt5_scalper.main
python monitor_mt5_live.py
```

---

## 🔴 EMERGENCY - If Something Goes Wrong

```powershell
# 1. IMMEDIATELY stop the bot
# Press Ctrl+C in the terminal where bot is running

# 2. Revert to dry_run
.\scripts\transition_mt5.ps1 -Mode revert

# 3. Close any open positions manually in MT5:
# Right-click position → Close Position

# 4. Check logs for errors
Get-Content logs/mt5_scalper.log -Tail 50
```

---

## 📈 What Success Looks Like

After 1-2 hours of monitoring, you should see:

```
✅ Closed Trades: 15-20 (depends on market activity)
✅ Win Rate: 40-60% (profitable range)
✅ Total P&L: Positive or break-even
✅ Signal Distribution: ~50% BUY, ~50% SELL
✅ No errors in logs
✅ MT5 connection stable
```

---

## 🚨 Red Flags - STOP IMMEDIATELY

- **P&L is -20% or worse** → STOP. Something is wrong.
- **Win rate drops below 30%** → Strategy not working. STOP.
- **All signals are BUY or SELL** → Signal drift. STOP.
- **"Connection refused" in logs** → MT5 disconnected. STOP.
- **Positions not closing** → Execution issue. STOP.

When any red flag occurs:
1. Ctrl+C to stop bot
2. Run `.\scripts\transition_mt5.ps1 -Mode revert`
3. Close positions manually
4. Investigate logs and config
5. DO NOT resume until root cause is found

---

## 🔍 Monitoring Dashboard Commands

```powershell
# Normal monitoring (10s refresh)
python monitor_mt5_live.py

# Fast monitoring (5s refresh) - intense trades
python monitor_mt5_live.py 5

# Ultra-fast (2s refresh) - for scalping
python monitor_mt5_live.py 2

# Check log for errors
Get-Content logs/mt5_scalper.log -Tail 100

# Live tail of logs (like Unix 'tail -f')
Get-Content logs/mt5_scalper.log -Wait -Tail 50
```

---

## 📋 Complete Checklist

Before you hit "GO LIVE", verify:

- [ ] MT5 terminal is running
- [ ] You're logged into MT5 account
- [ ] MT5 credentials are in `.env` (login, password, server)
- [ ] `config.toml` has correct settings
- [ ] Position size is SMALL (0.01 for first live trade)
- [ ] Max positions is limited (2-3)
- [ ] Stop-loss is configured
- [ ] Take-profit is configured
- [ ] You have 1-2 hours to monitor continuously
- [ ] You understand the red flags above
- [ ] You know how to close positions manually in MT5
- [ ] Logs are open and visible
- [ ] Dashboard is running in second terminal

---

## 💡 Pro Tips

1. **First trade is often test trade** - Don't panic if first few trades don't go perfectly
2. **Slippage is normal** - 1-2 pip slippage is expected on live accounts
3. **Scale gradually** - Don't jump from 0.01 to 1.0 lots
4. **Monitor continuously first 8 hours** - Watch for stability
5. **Log everything** - Save logs for analysis later
6. **Stay disciplined** - Don't override automated decisions
7. **Have exit plan** - Know exactly when you'll stop if losses occur

---

## Next Action Items

1. **Get MT5 credentials:**
   - Open MetaTrader5
   - Find your Login, Password, Server name

2. **Add to `.env`:**
   ```powershell
   # Edit .env and add your MT5 credentials
   notepad .env
   ```

3. **Run the check:**
   ```powershell
   .\scripts\transition_mt5.ps1 -Mode check
   ```

4. **Once check passes, read:**
   - `MT5_TRANSITION_GUIDE.md` (full detailed guide)

5. **Then start demo:**
   ```powershell
   .\scripts\transition_mt5.ps1 -Mode demo
   ```

---

## 📞 Questions?

- **Monitor not showing data?** Check that bot is running and state/mt5_scalper_state.json is being updated
- **MT5 connection fails?** Verify credentials in `.env` match your MT5 account exactly
- **Transition script fails?** Run with `-Mode check` to see what's missing
- **Logs show errors?** Check logs/mt5_scalper.log for specific error messages

Good luck! You're ready to go live! 🚀
