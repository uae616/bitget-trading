# Bitget Migration - User Checklist

## ✅ Pre-Deployment (Complete These Steps)

### 1. Credential Setup
- [ ] Get Bitget API credentials:
  - [ ] Go to https://www.bitget.com
  - [ ] Settings → API Management
  - [ ] Create new API Key with Spot + Futures permissions
  - [ ] Save: API Key, API Secret, Passphrase
  
- [ ] Update `.env` file in project root:
  ```env
  BITGET_API_KEY=your_key_here
  BITGET_API_SECRET=your_secret_here
  BITGET_API_PASSPHRASE=your_passphrase_here
  TELEGRAM_BOT_TOKEN=optional
  TELEGRAM_CHAT_ID=optional
  TELEGRAM_ENABLED=True
  ```
  - [ ] Verify file saved

### 2. Environment Verification
- [ ] Python 3.9+ installed
  ```powershell
  python --version
  ```
  
- [ ] Virtual environment activated:
  ```powershell
  .\scripts\setup_venv.ps1
  ```

- [ ] Dependencies installed:
  ```powershell
  pip install -r requirements.txt
  ```

### 3. Connectivity Test
- [ ] Run test script:
  ```powershell
  python -m scripts.test_bitget_client
  ```
  
- [ ] Verify output shows:
  - ✅ Credentials loaded
  - ✅ BitgetRestClient initialized
  - ✅ Ping successful
  - ✅ Account API access granted
  
- [ ] If test fails:
  - Check .env file syntax
  - Verify API key permissions in Bitget
  - Check IP whitelist in Bitget settings
  - See BITGET_INTEGRATION.md troubleshooting

### 4. Configuration Review
- [ ] Open `config.toml`
- [ ] Verify settings (no changes required, but review):
  - [ ] `dry_run = true` (important for testing!)
  - [ ] `base_url = "https://api.bitget.com"` (correct)
  - [ ] `coins = ["BTC", "ETH", "SOL", "BNB"]` (adjust if needed)
  - [ ] `cycle_seconds = 1` (trading frequency)
  - [ ] `daily_loss_limit_pct = 0.03` (3% max daily loss)

### 5. Initial Dry-Run (24-48 hours)
- [ ] Ensure `dry_run = true` in config.toml
- [ ] Start bot:
  ```powershell
  .\scripts\run_bitget_bot.ps1
  ```
  
- [ ] Monitor logs in real-time:
  ```powershell
  Get-Content logs\rebalance_bot.log -Tail 20 -Wait
  ```
  
- [ ] Verify bot is working:
  - [ ] Logs show price fetching
  - [ ] Logs show account sync
  - [ ] Logs show candle data loading
  - [ ] Logs show momentum calculations
  - [ ] Logs show buy/sell signals (or "no action")
  
- [ ] Run for 24-48 hours and:
  - [ ] Review simulated trades in logs
  - [ ] Verify fee calculations are reasonable (~0.2%)
  - [ ] Check position accounting accuracy
  - [ ] Ensure no critical errors

### 6. Pre-Live Safety Check
- [ ] Review bot logs for any errors
- [ ] Verify strategy behavior matches expectations
- [ ] Check position accounting is working
- [ ] Confirm risk guardrails are active (if applicable)
- [ ] Ensure you understand what bot will do with real money

### 7. Go Live (When Ready)
- [ ] **BACKUP YOUR STATE**:
  ```powershell
  Copy-Item state\bot_state.json state\bot_state.json.backup
  ```

- [ ] Update `config.toml`:
  ```toml
  [bot]
  dry_run = false  # ⚠️ REAL TRADING STARTS NOW
  ```

- [ ] Start with **small position sizes** (don't risk full account)

- [ ] Monitor first trades closely:
  - [ ] Watch logs in real-time
  - [ ] Verify orders are placed correctly
  - [ ] Check fills are accurate
  - [ ] Monitor fees and accounting
  
- [ ] Only increase position sizes after 24-48 hours of successful trading

---

## 📋 Daily Operations

### Starting the Bot
```powershell
# Activate venv if not already active
.\scripts\setup_venv.ps1

# Run bot
.\scripts\run_bitget_bot.ps1
```

### Monitoring
```powershell
# Watch logs in real-time
Get-Content logs\rebalance_bot.log -Tail 20 -Wait

# Or in another terminal, tail continuous
tail -f logs/rebalance_bot.log
```

### Stopping the Bot
- Press **Ctrl+C** in the terminal
- Wait for graceful shutdown (saves state)
- Logs will show "exiting" or "keyboard interrupt"

### Checking Bot Status
```powershell
# View latest log entries
Get-Content logs\rebalance_bot.log -Tail 50

# Check if process is running
Get-Process python | Where-Object {$_.CommandLine -match "main_bitget"}
```

---

## 🚨 Emergency Procedures

### Bot Not Starting
1. Check .env file has valid credentials
2. Run: `python -m scripts.test_bitget_client`
3. Check `logs/rebalance_bot.log` for errors
4. See BITGET_INTEGRATION.md troubleshooting section

### Strange Trading Behavior
1. Stop bot: **Ctrl+C**
2. Set `dry_run = true` temporarily
3. Run bot again to analyze behavior
4. Check logs and state file
5. Resume live trading once issue understood

### Position Tracking Wrong
1. Stop bot
2. Fetch account info directly from Bitget
3. Compare with `state/bot_state.json`
4. If large discrepancy, restore from backup
5. Contact support with details

### High Fees or Losses
1. Check logs for executed orders
2. Verify fees match Bitget's taker rate (~0.2%)
3. Review bot's position cost basis (WAC)
4. If unexpected, reduce trading activity
5. Investigate root cause

---

## 📞 Troubleshooting Quick Reference

| Problem | Quick Fix |
|---------|-----------|
| "API Key Invalid" | Check .env has correct credentials (no spaces) |
| "Signature failed" | Restart bot; client auto-syncs time |
| "Symbol not found" | Symbol doesn't exist on Bitget; check symbol list |
| "Order failed" | Check min notional, cooldown, or rate limits |
| "No trades executed" | Check logs for signals; verify prices; check filters |
| "Abnormal PnL" | Stop bot; review state; check fees; restore backup if needed |
| "Bot won't start" | Run test: `python -m scripts.test_bitget_client` |

---

## ✅ Final Sign-Off

Before going fully live:

- [ ] I have read BITGET_INTEGRATION.md
- [ ] I understand `dry_run` mode and its importance
- [ ] I have tested connectivity with test_bitget_client
- [ ] I ran the bot for 24-48 hours in dry_run mode
- [ ] I reviewed logs and understand the trading behavior
- [ ] I have backed up my state file
- [ ] I understand the fees (~0.2% per trade)
- [ ] I am ready to start real trading with `dry_run = false`

---

## 📚 Documentation Reference

| Question | Document |
|----------|----------|
| **How do I set up the bot?** | BITGET_INTEGRATION.md - Quick Start |
| **What symbols can I trade?** | BITGET_INTEGRATION.md - Trading Symbols |
| **How do I monitor the bot?** | BITGET_GUIDE.md - Logging |
| **What are the fees?** | BITGET_GUIDE.md - Safety Features |
| **Something broke!** | BITGET_INTEGRATION.md - Troubleshooting |
| **How does the strategy work?** | Original project README (unchanged) |
| **What's dry_run mode?** | BITGET_INTEGRATION.md - Dry-Run Mode |

---

## 🎓 Learning Resources

- **Bitget API Docs**: https://www.bitget.com/api-docs/spot/intro
- **Bitget Support**: https://www.bitget.com/support/center
- **Bot Logs**: Check `logs/rebalance_bot.log` for details
- **State File**: Check `state/bot_state.json` for account state

---

**Last Updated**: 2026-03-08
**Status**: Ready for Deployment ✅
