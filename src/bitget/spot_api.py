"""
Bitget Spot Trading API wrapper.
https://www.bitget.com/api-docs/spot/trade

Key differences from Binance:
- Symbol format: BTC-USDT (not BTCUSDT)
- Order response uses "orderId" (string)
- Quote order by amount may use "amount" instead of "quoteOrderQty"
- Account endpoint returns balances in different structure
"""

from .rest_client import BitgetRestClient


class BitgetSpotAPI:
    def __init__(self, rest_client: BitgetRestClient):
        self.client = rest_client

    # ---------- public endpoints ----------
    def exchange_info(self, symbol=None):
        """
        Get exchange info including symbol filters.
        
        Args:
            symbol: Optional symbol filter (e.g., "BTC-USDT")
        
        Returns:
            {"data": {"symbols": [...]}, "code": "00000", ...}
        """
        params = {}
        if symbol:
            params['symbol'] = symbol
        
        resp = self.client.public_get('/v2/spot/public/products', params=params)
        return resp

    def ticker_price(self, symbol: str):
        """
        Get current price for a symbol.
        
        Args:
            symbol: Trading pair (e.g., "BTC-USDT")
        
        Returns:
            {"data": {"symbol": "...", "lastPr": "50000"}, ...}
        """
        params = {'symbol': symbol}
        resp = self.client.public_get('/v2/spot/market/ticker', params=params)
        return resp

    def klines(self, symbol: str, interval: str = '15m', limit: int = 120):
        """
        Fetch OHLCV candles.
        
        Args:
            symbol: Trading pair (e.g., "BTC-USDT")
            interval: Candle interval (1m, 5m, 15m, 30m, 1h, 4h, 1d, etc.)
            limit: Number of candles (default 120)
        
        Returns:
            {"data": [[ts, open, high, low, close, volume], ...], ...}
        """
        params = {
            'symbol': symbol,
            'period': interval,
            'limit': limit
        }
        resp = self.client.public_get('/v2/spot/market/candles', params=params)
        return resp

    # ---------- account & balance endpoints ----------
    def account(self):
        """
        Get account info and balances.
        
        Returns:
            {
                "data": {
                    "balances": [
                        {
                            "coinId": "11",
                            "coin": "BTC",
                            "available": "1.0",
                            "frozen": "0.0",
                            "locked": "0.0"
                        },
                        ...
                    ]
                },
                "code": "00000",
                ...
            }
        """
        resp = self.client.signed_get('/v2/spot/account/info')
        return resp

    # ---------- order endpoints ----------
    def place_order(self, symbol: str, side: str, order_type: str, **kwargs):
        """
        Place a spot order (market or limit).
        
        Args:
            symbol: Trading pair (e.g., "BTC-USDT")
            side: "buy" or "sell"
            order_type: "market" or "limit"
            **kwargs: Additional params (quantity, price, amount, etc.)
        
        For market buy by amount:
            place_order("BTC-USDT", "buy", "market", amount="100")
        
        For market sell by quantity:
            place_order("BTC-USDT", "sell", "market", quantity="1.0")
        
        For limit order:
            place_order("BTC-USDT", "buy", "limit", quantity="1.0", price="50000")
        
        Returns:
            {"data": {"orderId": "123456", ...}, "code": "00000", ...}
        """
        body = {
            'symbol': symbol,
            'side': side,
            'orderType': order_type,
        }
        body.update(kwargs)
        
        resp = self.client.signed_post('/v2/spot/trade/orders', body=body)
        return resp

    def market_buy_quote(self, symbol: str, amount: float):
        """
        Market buy by quote amount (spend USDT, get BTC).
        
        Args:
            symbol: Trading pair (e.g., "BTC-USDT")
            amount: Quote amount to spend (e.g., 100 USDT)
        
        Returns:
            Market order response with fills
        """
        return self.place_order(
            symbol,
            side='buy',
            orderType='market',
            amount=str(amount)
        )

    def market_buy_qty(self, symbol: str, quantity: float):
        """
        Market buy by quantity (spend USDT, get exact amount of BTC).
        
        Args:
            symbol: Trading pair (e.g., "BTC-USDT")
            quantity: Amount of base asset to buy (e.g., 1.0 BTC)
        
        Returns:
            Market order response with fills
        """
        return self.place_order(
            symbol,
            side='buy',
            orderType='market',
            quantity=str(quantity)
        )

    def market_sell(self, symbol: str, quantity: float):
        """
        Market sell order.
        
        Args:
            symbol: Trading pair (e.g., "BTC-USDT")
            quantity: Amount to sell (e.g., 1.0 BTC)
        
        Returns:
            Market order response with fills
        """
        return self.place_order(
            symbol,
            side='sell',
            orderType='market',
            quantity=str(quantity)
        )

    def cancel_order(self, symbol: str, order_id: str):
        """
        Cancel an open order.
        
        Args:
            symbol: Trading pair
            order_id: Order ID to cancel
        
        Returns:
            Cancellation response
        """
        body = {
            'symbol': symbol,
            'orderId': order_id
        }
        resp = self.client.signed_post('/v2/spot/trade/cancel-orders', body=body)
        return resp

    def order_status(self, symbol: str, order_id: str):
        """
        Get order status.
        
        Args:
            symbol: Trading pair
            order_id: Order ID
        
        Returns:
            Order details including fills
        """
        params = {
            'symbol': symbol,
            'orderId': order_id
        }
        resp = self.client.signed_get('/v2/spot/trade/orders-details', params=params)
        return resp

    def open_orders(self, symbol: str = None):
        """
        Get all open orders.
        
        Args:
            symbol: Optional symbol filter
        
        Returns:
            List of open orders
        """
        params = {}
        if symbol:
            params['symbol'] = symbol
        
        resp = self.client.signed_get('/v2/spot/trade/open-orders', params=params)
        return resp
