class BotError(Exception):
    pass

class BinanceAPIError(BotError):
    def __init__(self, status_code: int, payload: str):
        super().__init__(f"Binance API error {status_code}: {payload}")
        self.status_code = status_code
        self.payload = payload
