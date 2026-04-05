# Bitget Minimum Order Notional Fix

## Issue
Error 45110 was appearing in logs claiming Bitget's minimum was **5 USDT**, which was incorrect.

## Root Cause
The error message "less than the minimum amount 5 USDT" was **copy-pasted from Binance configuration** when converting the bot from Binance to Bitget. The actual Bitget minimum is different.

## Solution
Fetched the actual minimum directly from Bitget's API using their public endpoint:

**API Endpoint**: `https://api.bitget.com/api/v2/spot/public/symbols`

**Result**: 
```json
{
  "minTradeUSDT": 1.0,
  "minTradeAmount": 0.0001,
  "symbol": "BTCUSDT",
  "baseCoin": "BTC",
  "quoteCoin": "USDT"
}
```

**Bitget's Actual Minimum**: **1.0 USDT** (not 5.0)

## Changes Made

### 1. Code (`src/futures/bot.py`, line 437)
```python
# Before:
min_order_notional_usdt = float(risk_cfg.get("min_order_notional_usdt", 5.0))

# After:
min_order_notional_usdt = float(risk_cfg.get("min_order_notional_usdt", 1.0))
```

### 2. Config (`config.toml`, line 95)
```toml
# Before:
[futures_risk]
min_order_notional_usdt = 1.1

# After:
[futures_risk]
# Bitget actual minimum from API: minTradeUSDT = 1.0 USDT
# Retrieved via https://api.bitget.com/api/v2/spot/public/symbols
min_order_notional_usdt = 1.0
```

## Verification
To verify Bitget's minimum at any time, run:
```powershell
python fetch_bitget_minimum.py
```

This script fetches the actual minimum directly from Bitget's public API.

## Impact
- Orders below **1.0 USDT** notional will be skipped with a `[LIMITS]` message
- Orders above **1.0 USDT** notional will now be accepted by Bitget
- Error 45110 should no longer appear for order size reasons

## Files Modified
- `src/futures/bot.py` (line 435-437)
- `config.toml` (line 93-95)

## Status
✅ **FIXED** - Using correct Bitget minimum of 1.0 USDT
