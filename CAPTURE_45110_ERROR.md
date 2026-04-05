# How to Capture and Debug Error 45110

## Steps to Run and Capture the Error

1. **Run the futures bot and capture full output**:
   ```powershell
   python -m src.main_futures 2>&1 | Tee-Object -FilePath logs/futures_error_45110.txt
   ```

2. **Let it run for 5-10 minutes** to generate multiple signal attempts

3. **Look for lines containing "45110"** in the logs:
   - The bot will catch the error and log the full exception message
   - Example: `[LIMITS] Skip LONG BTC/USDT:USDT due to exchange min notional (45110). Full error: ...`

4. **Share the error message** which will show:
   - The exact minimum amount Bitget requires
   - The order notional that was rejected
   - The symbol that failed

## What We're Looking For

The error message from Bitget will look like:
```
{"code":"45110","msg":"less than the minimum mamount 5 USDT"}
```

Or it might say a different amount like:
```
{"code":"45110","msg":"less than the minimum mamount 10 USDT"}
```

## After You Share the Error

Once we see the actual error message:
1. We'll extract the exact minimum amount Bitget requires
2. We'll update `min_order_notional_usdt` in `config.toml` to that value
3. The bot will then skip orders below that threshold automatically

## Current Settings to Check

Your current `config.toml` has:
```toml
[futures_risk]
risk_per_trade = 0.0075      # 0.75% risk per trade
min_order_notional_usdt = 1.1 # Current validation minimum
```

When an order is calculated:
- Order Notional = Quantity × Current Price
- If `Order Notional < min_order_notional_usdt`, the order is skipped (no API call)
- If it passes validation but Bitget rejects it, we catch error 45110

## Expected Logs During Run

You should see logs like:
```
[INFO] [DRY] Open LONG BTC/USDT:USDT qty=0.001234 price=40000.00 rsi=35.00 funding=0.0001
[INFO] [LIMITS] Skip LONG BTC/USDT:USDT notional=12.34 < min_notional=???.??
[WARNING] [LIMITS] Skip LONG ETH/USDT:USDT due to exchange min notional (45110), qty=0.001 notional=2.50. Full error: ...
```

The second or third format will show us the actual minimum.

## Temporary Logging (Optional)

If you want extra debug output, you can temporarily change the bot's log level to DEBUG by editing `config.toml`:
```toml
[futures_bot]
log_level = "DEBUG"  # More verbose output
```

Then revert to INFO after capturing the error.
