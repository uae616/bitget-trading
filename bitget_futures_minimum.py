import requests

def get_bitget_futures_minimums_v2(symbol: str, product_type: str = "USDT-FUTURES"):
    """
    Fetch minimum order size, min open value, precision, and contract specs
    for Bitget Futures using API v2.

    product_type must be:
        "USDT-FUTURES"
        "USDC-FUTURES"
        "COIN-FUTURES"
    """

    url = "https://api.bitget.com/api/v2/mix/market/contracts"
    params = {"productType": product_type}

    response = requests.get(url, params=params).json()

    print("DEBUG: API response keys =", response.keys())

    data = response.get("data")
    if data is None:
        raise ValueError(f"Bitget returned no data. Check productType='{product_type}'")

    for item in data:
        # v2 uses clean symbols like BTCUSDT, ETHUSDT
        if item["symbol"] == symbol:
            return {
                "symbol": symbol,
                "baseCoin": item["baseCoin"],
                "quoteCoin": item["quoteCoin"],
                "minTradeNum": float(item["minTradeNum"]),        # minimum contract size
                "minTradeUSDT": float(item["minTradeUSDT"]),      # minimum order value
                "pricePrecision": item["pricePlace"],             # price decimals
                "sizePrecision": item["volumePlace"],             # size decimals
                "sizeMultiplier": float(item["sizeMultiplier"]),  # correct multiplier field
                "makerFeeRate": item["makerFeeRate"],
                "takerFeeRate": item["takerFeeRate"],
            }

    return f"Contract {symbol} not found for productType {product_type}."


if __name__ == "__main__":
    result = get_bitget_futures_minimums_v2("BTCUSDT", "USDT-FUTURES")
    print("RESULT:", result)