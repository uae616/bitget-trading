# Bitget Integration Guide

This rebalance bot has been migrated from Binance to Bitget. All core functionality (Spot trading and Futures) is now supported via Bitget APIs.

## Quick Start

### 1. Update `.env` File

Replace the old Binance credentials with Bitget credentials:

```env
# Bitget API credentials
BITGET_API_KEY=your_api_key_here
BITGET_API_SECRET=your_api_secret_here
BITGET_API_PASSPHRASE=your_passphrase_here

# Telegram credentials (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ENABLED=True
```

**Getting Bitget Credentials:**
1. Log in to your Bitget account
2. Go to **Account → API** (or Settings → API)
3. Create a new API Key with these permissions:
   - **Spot Trading**: Read & Trade
   - **Futures Trading**: Read & Trade
   - **Account**: Read
4. Save the API Key, Secret, and Passphrase

### 2. Test Connection

```powershell
# Activate virtual environment
.\scripts\setup_venv.ps1

# Test Bitget client
python -m scripts.test_bitget_client
```

You should see output like:
```
✓ Credentials loaded from .env
✓ BitgetRestClient initialized
✓ Ping successful: 00000
✓ Server time: 1234567890123
✓ BitgetSpotAPI initialized
✓ Exchange info loaded: 250+ symbols
...
✅ Bitget client test passed!
```

### 3. Configure the Bot

Edit `config.toml` and update the exchange URL:

```toml
[bot]
base_url = "https://api.bitget.com"  # Already set for Bitget
dry_run = true  # Start with dry_run enabled!
cycle_seconds = 1
```

### 4. Run the Bot (Spot Trading)

```powershell
.\scripts\run_bitget_bot.ps1
```

The bot will:
- Fetch current balances from Bitget
- Monitor BTC, ETH, SOL, BNB (configured in `config.toml`)
- Execute spot trades based on momentum signals
- Log all activity to `logs/rebalance_bot.log`

### 5. Run Futures Bot (Optional)

For leveraged trading:

```powershell
.\scripts\run_futures_bot.ps1  # Uses CCXT currently
```

**Note**: Futures bot may need updating to use direct Bitget Futures API.

## Key Differences from Binance

### Symbol Format
- **Binance**: `BTCUSDT` (no separator)
- **Bitget**: `BTC-USDT` (dash-separated)

The bot handles this automatically—you don't need to change your coin list in `config.toml`.

### API Authentication
Bitget requires three credentials:
- API Key (used in header)
- API Secret (used in HMAC signature)
- Passphrase (also used in header for extra security)

### Order Response Format
Bitget order responses use slightly different field names:
- `filledAmount` instead of `executedQty`
- `filledTotal` instead of `cummulativeQuoteQty`
- `orderId` is always a string

The bot's execution layer automatically parses these.

### No Direct Convert API
Bitget doesn't have a direct "Convert" API like Binance. The bot skips this fallback for now. All trades use spot market orders.

## Architecture

### REST Client (`src/bitget/rest_client.py`)
- Low-level HTTP wrapper
- Handles HMAC-SHA256 signature generation
- Includes timestamp syncing and retries
- Supports both public and signed endpoints

### Spot API (`src/bitget/spot_api.py`)
- Account management (fetch balances)
- Market data (prices, OHLCV candles, exchange info)
- Order placement (market buy/sell)
- Order management (cancel, status)

### Futures API (`src/bitget/futures_api.py`)
- Perpetual futures trading
- Leverage and margin management
- Funding rate fetching
- Position management

### Data Utilities (`src/bitget/data.py`)
- Parse Bitget response formats into standardized structures
- Price and OHLCV caching
- Exchange filter parsing

### Main Bot (`src/main_bitget.py`)
- Replaces `src/main.py` for Bitget
- Initializes Bitget clients
- Runs the main trading loop
- Manages state and risk guardrails

## Trading Symbols

By default, the bot trades these pairs (configured in `config.toml`):

```toml
coins = ["BTC", "ETH", "SOL", "BNB"]
quote_asset = "USDT"
```

This translates to Bitget symbols:
- `BTC-USDT`
- `ETH-USDT`
- `SOL-USDT`
- `BNB-USDT`

To trade different pairs, edit `config.toml`:

```toml
coins = ["XRP", "ADA", "DOGE"]  # Your preferred coins
```

## Safety Features

### Dry Run Mode
Always start with `dry_run = true` in `config.toml`. The bot will:
- Fetch real prices and account data
- Calculate trades but **don't execute them**
- Log what it would have done

Once you're confident, set `dry_run = false` to trade.

### Risk Guardrails
- Daily loss limit: `daily_loss_limit_pct = 0.03` (3%)
- Max leverage: Capped at 5x (can't be overridden in config)
- Stop loss / take profit: Automatic position exits
- Drawdown pause: Halts trading if account drops too far

## Troubleshooting

### "Invalid API Key" Error
- Verify credentials are copied correctly (check spaces/quotes)
- Ensure API key has **Spot** and **Futures** permissions
- Check IP whitelist settings (may need to add your IP)

### "Request signature verification failed"
- Verify passphrase is correct
- Check system time sync (client auto-syncs with Bitget)
- Ensure API secret is copied exactly

### "Symbol not found"
- Verify symbol is available on Bitget (not all symbols from other exchanges exist)
- Check symbol format: should be like `BTC-USDT` with dash

### "Insufficient balance"
- In dry_run mode, this is expected behavior (no real orders)
- In live mode, ensure account has enough USDT for the configured min trade amount

## Logging

Logs are written to `logs/rebalance_bot.log` with the following levels:
- **INFO**: Normal operation, trade executions
- **WARNING**: Minor issues, skipped actions
- **ERROR**: Serious issues, cycle failures

Check logs for detailed information about what the bot is doing.

## Performance

Expected API call frequency (dry run):
- **Price updates**: 1 call per coin per cycle
- **Account balance**: 1 call per cycle
- **Candle data**: 1 call per coin per cycle (cached for 20s)
- **Exchange info**: 1 call on startup

Total: ~10-15 API calls per cycle (default 1 cycle/sec = 10-15 calls/sec max).

Bitget allows up to 300 requests per 10 seconds per IP, so this is well within limits.

## Next Steps

1. ✅ Set up `.env` with Bitget credentials
2. ✅ Test with `python -m scripts.test_bitget_client`
3. ✅ Run with `dry_run = true` first
4. ✅ Review logs in `logs/rebalance_bot.log`
5. ✅ Once confident, set `dry_run = false` for live trading

## Support

For issues:
1. Check the logs: `logs/rebalance_bot.log`
2. Review Bitget API docs: https://www.bitget.com/api-docs/spot/intro
3. Common issues are documented in the Troubleshooting section above

---

**Last Updated**: 2026-03-08
**Bitget API Version**: v2
**Bot Version**: Bitget-enabled
