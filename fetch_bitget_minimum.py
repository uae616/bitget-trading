#!/usr/bin/env python3
"""Fetch actual minimum order notional from Bitget using proper validator"""

import requests

def round_to_precision(value: float, precision: int) -> float:
    """Round a number to the required decimal precision."""
    return float(f"{value:.{precision}f}")


def validate_order(
    side: str,
    price: float,
    quantity: float,
    min_qty: float,
    min_notional: float,
    price_precision: int,
    qty_precision: int,
):
    """
    Validate and correct an order before sending it to Bitget.
    Works for both Spot and Futures.

    Returns:
        dict with corrected price, quantity, and validation flags.
    """

    # 1. Round price and quantity
    price = round_to_precision(price, price_precision)
    quantity = round_to_precision(quantity, qty_precision)

    # 2. Enforce minimum quantity
    if quantity < min_qty:
        quantity = min_qty

    # 3. Enforce minimum notional
    notional = price * quantity
    if notional < min_notional:
        quantity = round_to_precision(min_notional / price, qty_precision)

    # 4. Recompute notional after adjustments
    notional = price * quantity

    return {
        "side": side,
        "price": price,
        "quantity": quantity,
        "notional": notional,
        "valid": notional >= min_notional and quantity >= min_qty,
    }


def get_bitget_minimum_notional(symbol: str = "BTCUSDT", product_type: str = "usdt-futures"):
    """
    Fetch minimum order notional from Bitget Futures API
    Uses the validator to calculate actual minimum notional
    """
    try:
        # Correct Bitget Futures endpoint
        url = "https://api.bitget.com/api/v2/mix/market/contracts"
        params = {"productType": product_type, "symbol": symbol}
        
        print(f"Fetching {product_type} for {symbol}")
        print(f"URL: {url}\n")
        
        response = requests.get(url, params=params).json()
        
        if response.get("code") != "00000":
            print(f"❌ Error from API: {response}")
            return None
        
        data = response.get("data", [])
        if not data:
            print(f"❌ No data returned for {symbol}")
            return None
        
        item = data[0]
        print("✅ CONTRACT INFO FROM API:")
        print(f"  symbol: {item.get('symbol')}")
        print(f"  baseCoin: {item.get('baseCoin')}")
        print(f"  quoteCoin: {item.get('quoteCoin')}")
        print(f"  minTradeNum: {item.get('minTradeNum')}")
        print(f"  priceScale: {item.get('priceScale')}")
        print(f"  volumeScale: {item.get('volumeScale')}")
        
        min_qty = float(item.get("minTradeNum", 0.0001))
        price_precision = int(item.get("priceScale", 2))
        qty_precision = int(item.get("volumeScale", 4))
        
        # Use current price to validate minimum notional
        # Get current price from market
        ticker_url = "https://api.bitget.com/api/v2/mix/market/ticker"
        ticker_response = requests.get(ticker_url, params={"symbol": symbol}).json()
        
        if ticker_response.get("code") == "00000":
            current_price = float(ticker_response.get("data", [{}])[0].get("lastPr", 1))
        else:
            current_price = 1  # Fallback
        
        print(f"  Current price: {current_price}")
        
        # Test with minimum quantity to find minimum notional
        test_order = validate_order(
            side="buy",
            price=current_price,
            quantity=min_qty,
            min_qty=min_qty,
            min_notional=0.01,  # Start with 0.01 USDT
            price_precision=price_precision,
            qty_precision=qty_precision,
        )
        
        min_notional = test_order["notional"]
        
        print(f"\n✅ BITGET {product_type.upper()} MINIMUMS:")
        print(f"  Min Quantity: {min_qty}")
        print(f"  Min Notional: {min_notional} USDT")
        print(f"  Price Precision: {price_precision}")
        print(f"  Qty Precision: {qty_precision}")
        
        return min_notional
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # Test futures
    futures_min = get_bitget_minimum_notional("BTCUSDT", "usdt-futures")
    
    print("\n" + "="*80)
    
    # Test spot
    spot_min = get_bitget_minimum_notional("BTCUSDT", "spot")
    
    print("\n" + "="*80)
    print("\nUSE IN config.toml:")
    if futures_min:
        print(f"[futures_risk]")
        print(f"min_order_notional_usdt = {futures_min}")
    if spot_min:
        print(f"\n[risk]")
        print(f"min_order_notional_usdt = {spot_min}")


