import time

class PriceCache:
    def __init__(self, spot_api, ttl_sec: float = 3.0):
        self.spot_api = spot_api
        self.ttl = ttl_sec
        self.cache = {}  # symbol -> (price, expire_ts)

    def get_last_price(self, symbol: str) -> float:
        now = time.time()
        item = self.cache.get(symbol)
        if item and item[1] > now:
            return item[0]

        data = self.spot_api.ticker_price(symbol)
        price = float(data['price'])
        self.cache[symbol] = (price, now + self.ttl)
        return price
