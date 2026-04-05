# Quick Start: Bitget Trading Bot with CCXT

## Prerequisites
- Python 3.10+
- Virtual environment activated
- `.env` file with credentials

## Setup (First Time)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Create/verify `.env` file:
```
BITGET_API_KEY=bg_xxxxx
BITGET_API_SECRET=xxxxx
BITGET_API_PASSPHRASE=xxxxx
TELEGRAM_ENABLED=True
TELEGRAM_BOT_TOKEN=xxxxx  (optional)
TELEGRAM_CHAT_ID=xxxxx    (optional)
```

### 3. Verify Configuration
```bash
python scripts/test_ccxt_bitget_live.py
```

Expected output:
```
✅ All CCXT Bitget tests passed!
```

## Running the Bot

### Option A: Dry-Run Mode (Recommended for Testing)
```bash
# Edit config.toml: dry_run = true
python -m src.main_bitget
```

Watch for:
- `✅ Bitget exchange initialized via CCXT`
- Price updates and strategy decisions
- Simulated trades (no real money)

### Option B: Live Trading Mode
```bash
# Edit config.toml: dry_run = false
# Verify small amounts first!
python -m src.main_bitget
```

Watch logs for:
- Actual order placements
- P&L tracking
- Risk guardrail alerts

## Common Commands

### Test Connectivity
```bash
python scripts/test_ccxt_bitget_live.py
```

### Test Full Integration
```bash
python scripts/test_ccxt_integration.py
```

### Check Bot Logs
```bash
tail -f logs/rebalance.log
```

### Check Trading State
```bash
cat state/state.json | python -m json.tool
```

## Key Files

- `config.toml` - Strategy & exchange settings
- `.env` - API credentials (DO NOT COMMIT!)
- `src/main_bitget.py` - Bot entry point
- `src/core/settings.py` - Configuration loader
- `logs/rebalance.log` - Bot activity log
- `state/state.json` - Trading state (positions, P&L)

## Configuration Tweaks

### Reduce Trade Frequency
```toml
[bot]
cycle_seconds = 5  # Default: 1 (check every second)
```

### Change Coins
```toml
[portfolio]
coins = ["BTC", "ETH"]  # Default: ["BTC", "ETH", "SOL", "BNB"]
```

### Adjust Buy Amount
```toml
[dip_buy]
min_buy_usdt = 10.0  # Default: 5.1 (Bitget minimum ~1.0)
```

### Disable Features
```toml
[profit_take]
enabled = false  # Disable profit taking

[dip_buy]
enabled = false  # Disable dip buying

[risk]
enabled = false  # Disable risk guardrails
```

## Monitoring

### Real-Time Logs
```bash
python -m src.main_bitget 2>&1 | tee output.log
```

### Key Metrics in Logs
- `[TRACE]` - Strategy state (cash, positions, ranked coins)
- `[DECISION]` - Trade decisions (SELL/BUY actions)
- `[SELL]` / `[BUY]` - Order placements
- `[RISK]` - Risk guardrail evaluations
- `[ERROR]` - Any errors or issues

### Check Trading History
```bash
# View state.json
python -c "
import json
with open('state/state.json') as f:
    state = json.load(f)
    print(f'Cycle: {state[\"meta\"].get(\"cycle\", 0)}')
    print(f'Cash: {state.get(\"cash_usdt\", 0):.2f} USDT')
    print(f'Positions: {state.get(\"positions\", {})}')
    print(f'Total PnL: {state[\"pnl\"].get(\"fees_usdt\", 0):.2f} USDT')
"
```

## Stopping the Bot

Press `Ctrl+C` - bot will:
1. Save state to `state/state.json`
2. Release single-instance lock
3. Exit gracefully

## Troubleshooting

### "403 Forbidden" Error
→ **Should NOT happen with CCXT** - if it does, check .env credentials

### "Market not found"
→ Check coin exists on Bitget, update `coins` in config.toml

### "Insufficient funds"
→ Add USDT to account or reduce `min_buy_usdt`

### "Minimum notional not met"
→ Normal warning - orders too small, skipped safely

### Bot won't start
→ Run `python scripts/test_ccxt_integration.py` to diagnose

## Performance

**Typical cycle time**: 1-2 seconds per check
- 0.5s - Fetch prices
- 0.3s - Fetch klines
- 0.2s - Calculate strategy
- 0.5s - Execute trades

**API calls per hour**: ~3,600 (one per second)
- Bitget rate limit: 30 req/s (plenty of margin)

## Risk Management

Bot includes built-in protections:
- ✅ Daily loss limit (3% default)
- ✅ Min position floor ($5.1)
- ✅ Max trade per cycle limits
- ✅ Cooldown between trades (300s)
- ✅ Dry-run mode for testing

## What to Monitor

1. **Account Balance** - Check Bitget app regularly
2. **P&L** - Review `state.json` daily
3. **Logs** - Watch for `[ERROR]` messages
4. **Risk Alerts** - Telegram notifications (if enabled)

## Support Resources

- **CCXT Docs**: https://docs.ccxt.com/
- **Bitget API**: https://www.bitget.com/en/spot/BTCUSDT
- **Bot Docs**: See `CCXT_MIGRATION.md`

---

**Version**: 1.0 (CCXT-based)
**Last Updated**: 2026-03-10
**Status**: ✅ Production Ready
