import requests

TRUE_MINIMUMS = {
    "BTC": 0.0001,
    "ETH": 0.001,
    "BNB": 0.01,
    "SOL": 0.01,
    "XRP": 1,
    "ADA": 1,
}

def get_bitget_minimums_v2(symbol: str):
    url = "https://api.bitget.com/api/v2/spot/public/symbols"
    response = requests.get(url).json()

    for item in response.get("data", []):
        if item["symbol"] == symbol:
            base = item["baseCoin"]
            quote = item["quoteCoin"]

            min_amount = float(item["minTradeAmount"])
            min_usdt = float(item["minTradeUSDT"])

            print("DEBUG: API minTradeAmount =", min_amount)
            print("DEBUG: baseCoin =", base)

            # Apply fallback
            if min_amount == 0.0:
                if base in TRUE_MINIMUMS:
                    print("DEBUG: Using TRUE_MINIMUMS fallback")
                    min_amount = TRUE_MINIMUMS[base]
                else:
                    print("DEBUG: No fallback found for base =", base)

            return {
                "symbol": symbol,
                "baseCoin": base,
                "quoteCoin": quote,
                "minTradeAmount": min_amount,
                "minTradeUSDT": min_usdt,
                "pricePrecision": item["pricePrecision"],
                "quantityPrecision": item["quantityPrecision"],
            }

    return f"Symbol {symbol} not found."


# 🔥 THIS PART MUST EXIST — otherwise nothing runs
if __name__ == "__main__":
    result = get_bitget_minimums_v2("BTCUSDT")
    print("RESULT:", result)