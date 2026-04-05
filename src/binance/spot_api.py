from ..utils.symbols import spot_symbol


class SpotAPI:
    def __init__(self, client, quote_asset="USDT"):
        self.client = client
        self.quote_asset = quote_asset

    # ---------- public market data ----------
    def exchange_info(self):
        return self.client.public_get("/api/v3/exchangeInfo")

    def ticker_price(self, symbol: str):
        return self.client.public_get("/api/v3/ticker/price", {"symbol": symbol})

    def klines(self, symbol: str, interval: str, limit: int = 120):
        return self.client.public_get(
            "/api/v3/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )

    # ---------- signed account/trading ----------
    def account(self):
        return self.client.signed_get("/api/v3/account")

    def market_sell(self, coin: str, qty: float, quote: str = None):
        sym = spot_symbol(coin, quote or self.quote_asset)
        params = {
            "symbol": sym,
            "side": "SELL",
            "type": "MARKET",
            "quantity": qty,
            "newOrderRespType": "FULL",
        }
        return self.client.signed_post("/api/v3/order", params)

    def market_buy_quote(self, coin: str, quote_qty: float, quote: str = None):
        sym = spot_symbol(coin, quote or self.quote_asset)
        params = {
            "symbol": sym,
            "side": "BUY",
            "type": "MARKET",
            "quoteOrderQty": quote_qty,
            "newOrderRespType": "FULL",
        }
        return self.client.signed_post("/api/v3/order", params)

    def market_buy_qty(self, coin: str, qty: float, quote: str = None):
        sym = spot_symbol(coin, quote or self.quote_asset)
        params = {
            "symbol": sym,
            "side": "BUY",
            "type": "MARKET",
            "quantity": qty,
            "newOrderRespType": "FULL",
        }
        return self.client.signed_post("/api/v3/order", params)
