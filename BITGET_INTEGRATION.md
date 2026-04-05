# Bitget Integration Complete ✅

Your rebalance bot has been successfully migrated from Binance to Bitget. This document provides a quick-start guide and technical reference.

## 🚀 Quick Start (5 minutes)

### 1. Update `.env` File
Create or update `.env` in the project root:

```env
# Bitget credentials (required)
BITGET_API_KEY=your_key
BITGET_API_SECRET=your_secret
BITGET_API_PASSPHRASE=your_passphrase

# Telegram (optional)
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ENABLED=True
```

### 2. Get Bitget Credentials
1. Log in to https://www.bitget.com
2. Settings → API Management
3. Create new API Key with:
   - **Permissions**: Spot Trade, Futures Trade, Account Read
   - **IP Whitelist**: Add your IP (or leave empty)
4. Save: API Key, API Secret, Passphrase

### 3. Test Connectivity
```powershell
# Activate virtual environment (if not already)
.\scripts\setup_venv.ps1

# Test Bitget client
python -m scripts.test_bitget_client
```

Expected output:
```
✓ Credentials loaded from .env
✓ BitgetRestClient initialized
✓ Ping successful: 00000
✓ Account API access granted
✅ Bitget client test passed!
```

### 4. Run the Bot
```powershell
.\scripts\run_bitget_bot.ps1
```

Logs appear in: `logs/rebalance_bot.log`

## 📋 Configuration

### config.toml (No Changes Required)

Your existing configuration is compatible. Key settings:

```toml
[bot]
cycle_seconds = 1
dry_run = true              # Set to false for live trading
base_url = "https://api.bitget.com"

[portfolio]
coins = ["BTC", "ETH", "SOL", "BNB"]
quote_asset = "USDT"
```

### Symbol Mapping (Automatic)

Your config uses: `BTC`, `ETH`, etc.
Bot converts to Bitget format: `BTC-USDT`, `ETH-USDT`

**No manual symbol conversion needed!**

## 📚 What's New

### New Files Created
```
src/bitget/                     # New Bitget integration module
├── __init__.py
├── rest_client.py              # Low-level HTTP client
├── spot_api.py                 # Spot trading wrapper
├── futures_api.py              # Futures trading wrapper
└── data.py                      # Response parsing & caching

src/main_bitget.py              # New entry point for bot
src/engine/execution_bitget.py   # Bitget-aware trade execution

scripts/
├── run_bitget_bot.ps1          # New launcher script
└── test_bitget_client.py       # New connectivity test

BITGET_GUIDE.md                 # Detailed documentation
BITGET_INTEGRATION.md           # This file
```

### Updated Files
```
src/core/settings.py            # Now loads Bitget credentials
.env.example                    # Updated with Bitget vars
```

### Unchanged Files (Fully Compatible)
```
src/main.py                     # Original Binance entry point
src/engine/execution.py         # Original execution logic
All strategy/engine files       # Unchanged
All core utilities              # Unchanged
```

## 🔧 Technical Details

### REST Client (`src/bitget/rest_client.py`)

**Authentication Pattern**:
```
Message = timestamp + method + path + body
Signature = base64(HMAC-SHA256(message, secret))
Headers = X-BITGET-APIKEY, X-BITGET-SIGN, X-BITGET-TIMESTAMP, X-BITGET-PASSPHRASE
```

**Key Methods**:
- `ping()` - Health check
- `server_time()` - Get server timestamp (auto-synced)
- `sync_time()` - Sync client clock with server
- `signed_get()` / `signed_post()` - Authenticated requests
- `public_get()` - Public endpoints

### Spot API (`src/bitget/spot_api.py`)

**Trading Methods**:
- `account()` - Get balances
- `exchange_info()` - Get symbols and filters
- `ticker_price(symbol)` - Current price
- `klines(symbol, interval, limit)` - OHLCV data
- `market_buy_quote(symbol, amount)` - Buy by USDT amount
- `market_sell(symbol, quantity)` - Sell by coin amount
- `place_order()` - Generic order placement

**Response Format (Bitget)**:
```python
{
    "code": "00000",  # Success code
    "msg": "success",
    "data": {
        "symbol": "BTC-USDT",
        "orderId": "123456",
        "filledAmount": "1.0",      # Executed quantity
        "filledTotal": "50000.0",   # Executed notional
        "fees": "10.0",             # Commission
        "feesCoin": "USDT",
        "status": "filled"
    }
}
```

### Futures API (`src/bitget/futures_api.py`)

**Key Methods**:
- `account_info()` - Account balance
- `positions()` - Open positions
- `set_leverage(symbol, leverage)` - Set leverage (1-5x)
- `place_order()` - Market/limit orders
- `close_position(symbol)` - Close with market order
- `funding_rate(symbol)` - Current funding rate
- `klines()` - Historical candles

### Data Parsing (`src/bitget/data.py`)

Utilities to parse Bitget responses:
- `parse_bitget_exchange_info()` - Extract filters
- `parse_bitget_ticker()` - Get price
- `parse_bitget_klines()` - Get OHLCV
- `parse_bitget_account()` - Get balances
- `parse_bitget_order()` - Parse order response
- `BitgetPriceCache` - Price caching
- `BitgetKlineCache` - Candle caching

## 🎯 Trading Flow

### Spot Trading Execution

1. **Fetch Account** → Get balances
2. **Fetch Prices** → Get current prices
3. **Fetch Candles** → Calculate momentum
4. **Strategy Decision** → Decide buy/sell
5. **Validate Order**
   - Check min notional
   - Check symbol filters
   - Check cooldown
6. **Place Order** → Market buy/sell via Bitget
7. **Parse Response** → Extract fills, fees
8. **Update State** → WAC accounting, positions
9. **Save State** → Persist to state file

### Dry-Run Mode

In `dry_run = true`:
- Real API calls for prices, account, candles
- Orders are **simulated** (not placed)
- State updates with simulated fills
- Safe way to test before live trading

### Live Mode

In `dry_run = false`:
- All API calls same as dry-run
- Orders are **actually placed**
- Real fills from Bitget
- Real fees charged

## 🛡️ Safety Features

### Built-in Protections

1. **Dry-Run Mode** (default)
   - Test before trading for real
   - Simulates fills with real prices
   - 24-48 hour recommended testing period

2. **Daily Loss Limit**
   - Default: 3% of account equity
   - Halts trading if exceeded
   - Resets daily at UTC midnight

3. **Cooldown Between Trades**
   - Default: 300 seconds (5 minutes)
   - Prevents spam trading same coin
   - Configurable per symbol

4. **Position Limits**
   - Min trade: 5.1 USDT (configurable)
   - Max leverage: 5x (hard-coded, can't override)
   - Reserve cash: 10% kept aside

5. **Risk Guardrails**
   - Momentum floor check
   - Trend validation
   - Entry signal thresholds

## 📊 Monitoring

### Log Files
```
logs/rebalance_bot.log         # Main bot activity
```

### Log Levels
- **INFO**: Trade executions, important events
- **WARNING**: Skipped actions, minor issues
- **ERROR**: Failed orders, API errors

### Key Metrics (in state file)
- `cash_usdt` - Available USDT
- `positions[coin]` - Coin holdings and cost basis
- `pnl.fees_usdt` - Accumulated trading fees
- `meta.cycle` - Current cycle count

## ❓ Common Questions

### Q: How do I enable live trading?
**A**: Set `dry_run = false` in `config.toml`. Recommended to run 24-48h in dry-run first.

### Q: What symbols can I trade?
**A**: Any symbol available on Bitget. Check exchange-info for available pairs.

### Q: How often does the bot trade?
**A**: Every `cycle_seconds` (default 1s), bot checks if buy/sell signals exist and executes if conditions met.

### Q: What are the fees?
**A**: Bitget standard maker/taker fees (~0.2%). Actual fees charged by Bitget and tracked in state.

### Q: Can I use multiple coins?
**A**: Yes! Edit `config.toml` coins array. Default: BTC, ETH, SOL, BNB.

### Q: What if my API key doesn't work?
**A**: 
1. Verify copy accuracy (no spaces/quotes)
2. Check API key has Spot + Futures permissions
3. Check IP whitelist settings
4. Run test: `python -m scripts.test_bitget_client`

### Q: How do I monitor the bot?
**A**: Check logs in real-time: `tail -f logs/rebalance_bot.log`

## 🚨 Troubleshooting

| Issue | Solution |
|-------|----------|
| "Signature failed" | System time out of sync. Client auto-syncs; restart bot if persists. |
| "API key rejected" | Check .env copy accuracy. Whitelist your IP in Bitget settings. |
| "Symbol not found" | Symbol doesn't exist on Bitget. Check exchange-info. |
| "Insufficient balance" | (Dry-run OK) For live: ensure account has min balance. |
| "Order failed" | Check min notional, cooldown period, or API rate limits. |
| "No log output" | Verify venv is activated. Check bot started with `run_bitget_bot.ps1`. |

## 📞 Support Resources

- **Bitget API Docs**: https://www.bitget.com/api-docs/spot/intro
- **Bitget Support**: https://www.bitget.com/support/center
- **Bot Logs**: `logs/rebalance_bot.log` (detailed debug info)
- **Test Script**: `python -m scripts.test_bitget_client` (verify connectivity)

## 🔄 Fallback to Binance

The original Binance integration is still available:
```powershell
# Old Binance bot (still works)
.\scripts\run_bot.ps1

# New Bitget bot
.\scripts\run_bitget_bot.ps1
```

Both can coexist. Use `.env` credentials that match your active exchange.

## ✅ Verification Checklist

Before going live:

- [ ] `.env` file has valid Bitget credentials
- [ ] `python -m scripts.test_bitget_client` passes
- [ ] `config.toml` has `dry_run = true`
- [ ] Bot runs without errors: `.\scripts\run_bitget_bot.ps1`
- [ ] Logs show price fetching and account sync
- [ ] Logs show strategy decisions (buy/sell signals)
- [ ] Run for 24-48 hours in dry-run mode
- [ ] Review simulated trades in logs
- [ ] Verify fees and position accounting
- [ ] Once confident, set `dry_run = false`
- [ ] Start with small positions
- [ ] Monitor live trading closely

## 📝 Version Info

- **Integration Date**: 2026-03-08
- **Bitget API Version**: v2
- **Bot Version**: Bitget-enabled
- **Python**: 3.9+
- **Dependencies**: requests, python-dotenv, pandas, numpy, ccxt

## 🎓 Learning Resources

1. **BITGET_GUIDE.md** - Full feature guide
2. **src/bitget/rest_client.py** - REST client internals
3. **src/bitget/spot_api.py** - Spot trading API
4. **src/bitget/futures_api.py** - Futures API
5. **src/main_bitget.py** - Bot main loop
6. **src/engine/execution_bitget.py** - Execution logic

---

**Status**: ✅ Production Ready

Start with dry_run mode, test thoroughly, then go live with confidence!
