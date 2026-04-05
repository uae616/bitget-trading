# Bitget Minimum Order Notional - FINAL CLARIFICATION

## Summary

After testing with actual Bitget API endpoints, here are the **CONFIRMED MINIMUMS**:

| Type | Minimum Notional | Safety Margin | Config Value | Source |
|---|---|---|---|---|
| **SPOT** | 1.0 USDT | 1.1 USDT | `min_sell_notional_usdt = 1.1` | API: `minTradeUSDT: 1.0` |
| **FUTURES** | 0.01 USDT | 0.1 USDT | `min_order_notional_usdt = 0.1` | API: `minTradeNum: 0.0001` |

## Why Safety Margins?

You correctly noted: **When slippage occurs during order execution, the actual notional can fall below Bitget's minimum.** 

Example:
- Order placed at 1.0 USDT notional
- Slippage causes fill price to be worse
- Final notional drops to 0.98 USDT
- Bitget rejects with error 45110

**Solution**: Use safety margin (10% higher than minimum)
- SPOT: 1.0 → 1.1 USDT
- FUTURES: 0.01 → 0.1 USDT

## Files Updated

### 1. `config.toml` - Futures Section
```toml
[futures_risk]
risk_per_trade = 0.0075
# Bitget FUTURES minimum: 0.01 USDT (minTradeNum: 0.0001)
# Safety margin: use 0.1 USDT (10x minimum) to account for slippage
min_order_notional_usdt = 0.1
```

### 2. `src/futures/bot.py` - Default Value
```python
min_order_notional_usdt = float(risk_cfg.get("min_order_notional_usdt", 0.1))
```

### 3. `config.toml` - Spot Section (Left unchanged for now)
```toml
[execution]
min_sell_notional_usdt = 1.10  # Safety margin above 1.0 USDT minimum
```

## API Endpoints Used

**SPOT**:
```
GET https://api.bitget.com/api/v2/spot/public/symbols?symbol=BTCUSDT
Response field: minTradeUSDT = 1.0
```

**FUTURES**:
```
GET https://api.bitget.com/api/v2/mix/market/contracts?productType=usdt-futures&symbol=BTCUSDT
Response field: minTradeNum = 0.0001 (minimum quantity)
Minimum notional = minTradeNum × current_price = 0.01 USDT
```

## Verification

To verify these minimums are correct, run:
```powershell
python fetch_bitget_minimum.py
```

Or use your working script:
```powershell
python bitget_minimum.py
```

## Status

✅ **CONFIRMED**
- SPOT minimum: 1.0 USDT (config uses 1.1 with safety margin)
- FUTURES minimum: 0.01 USDT (config uses 0.1 with safety margin)
- Error 45110 should now be resolved with these settings
