"""
Bitget Futures Trading API wrapper.
https://www.bitget.com/api-docs/mix/intro

Key Bitget Futures features:
- Symbol format: BTC-USDT:USDT (perpetual), BTC-USDT-231225 (quarterly)
- Margin mode: isolated or cross
- Position mode: one-way (unidirectional) or hedge (long+short)
- Leverage: can be set per symbol or per position
"""

from .rest_client import BitgetRestClient


class BitgetFuturesAPI:
    def __init__(self, rest_client: BitgetRestClient, product_type: str = 'umcbl'):
        """
        Initialize Bitget Futures API.
        
        Args:
            rest_client: BitgetRestClient instance
            product_type: 'umcbl' (USDT perpetual), 'dmcbl' (USDC perpetual)
        """
        self.client = rest_client
        self.product_type = product_type

    # ---------- account endpoints ----------
    def account_info(self):
        """
        Get account info and balances.
        
        Returns:
            {"data": {"availableBalance": "1000", "totalBalance": "1000"}, ...}
        """
        params = {'productType': self.product_type}
        resp = self.client.signed_get('/v2/mix/account/accounts', params=params)
        return resp

    def positions(self, symbol: str = None):
        """
        Get all open positions.
        
        Args:
            symbol: Optional symbol filter (e.g., "BTC-USDT:USDT")
        
        Returns:
            {
                "data": [
                    {
                        "symbol": "BTC-USDT:USDT",
                        "side": "long",  # or "short"
                        "positionQty": "1.0",
                        "entryPrice": "50000",
                        "marginMode": "isolated",
                        "leverage": "3",
                        "unrealizedPL": "500",
                        ...
                    },
                    ...
                ],
                ...
            }
        """
        params = {'productType': self.product_type}
        if symbol:
            params['symbol'] = symbol
        
        resp = self.client.signed_get('/v2/mix/positions', params=params)
        return resp

    def position_info(self, symbol: str):
        """
        Get info for a specific position.
        
        Args:
            symbol: Symbol (e.g., "BTC-USDT:USDT")
        
        Returns:
            Position details
        """
        params = {
            'productType': self.product_type,
            'symbol': symbol
        }
        resp = self.client.signed_get('/v2/mix/positions', params=params)
        return resp

    # ---------- trading endpoints ----------
    def place_order(self, symbol: str, side: str, order_type: str, size: float, **kwargs):
        """
        Place a futures order.
        
        Args:
            symbol: Trading pair (e.g., "BTC-USDT:USDT")
            side: "buy" or "sell"
            order_type: "market" or "limit"
            size: Quantity to trade
            **kwargs: Additional params (price, reduceOnly, leverage, etc.)
        
        Returns:
            {"data": {"orderId": "123456", ...}, ...}
        """
        body = {
            'symbol': symbol,
            'side': side,
            'orderType': order_type,
            'size': str(size),
            'productType': self.product_type,
        }
        body.update(kwargs)
        
        resp = self.client.signed_post('/v2/mix/orders/place-order', body=body)
        return resp

    def market_buy(self, symbol: str, size: float, **kwargs):
        """Market buy order."""
        return self.place_order(symbol, side='buy', order_type='market', size=size, **kwargs)

    def market_sell(self, symbol: str, size: float, **kwargs):
        """Market sell order."""
        return self.place_order(symbol, side='sell', order_type='market', size=size, **kwargs)

    def limit_buy(self, symbol: str, size: float, price: float, **kwargs):
        """Limit buy order."""
        return self.place_order(symbol, side='buy', order_type='limit', size=size, price=str(price), **kwargs)

    def limit_sell(self, symbol: str, size: float, price: float, **kwargs):
        """Limit sell order."""
        return self.place_order(symbol, side='sell', order_type='limit', size=size, price=str(price), **kwargs)

    def close_position(self, symbol: str, size: float = None, **kwargs):
        """
        Close a position (market order with reduceOnly=true).
        
        Args:
            symbol: Trading pair
            size: Position size (if None, closes entire position)
        
        Returns:
            Order confirmation
        """
        params = {'reduceOnly': 'true'}
        params.update(kwargs)
        
        if size is None:
            # Fetch position and use its quantity
            pos = self.position_info(symbol)
            if 'data' in pos and len(pos['data']) > 0:
                size = float(pos['data'][0].get('positionQty', 0))
        
        return self.place_order(
            symbol,
            side='sell' if size > 0 else 'buy',  # Opposite side to close
            order_type='market',
            size=abs(size),
            **params
        )

    def cancel_order(self, symbol: str, order_id: str):
        """
        Cancel an open order.
        
        Args:
            symbol: Trading pair
            order_id: Order ID
        
        Returns:
            Cancellation response
        """
        body = {
            'symbol': symbol,
            'orderId': order_id,
            'productType': self.product_type
        }
        resp = self.client.signed_post('/v2/mix/orders/cancel-order', body=body)
        return resp

    def order_status(self, symbol: str, order_id: str):
        """
        Get order status.
        
        Args:
            symbol: Trading pair
            order_id: Order ID
        
        Returns:
            Order details
        """
        params = {
            'symbol': symbol,
            'orderId': order_id,
            'productType': self.product_type
        }
        resp = self.client.signed_get('/v2/mix/orders/details', params=params)
        return resp

    # ---------- leverage & margin ----------
    def set_leverage(self, symbol: str, leverage: int, margin_mode: str = 'isolated'):
        """
        Set leverage for a symbol.
        
        Args:
            symbol: Trading pair
            leverage: Leverage level (e.g., 1, 3, 5)
            margin_mode: 'isolated' or 'cross'
        
        Returns:
            Leverage confirmation
        """
        body = {
            'symbol': symbol,
            'leverage': str(leverage),
            'marginMode': margin_mode,
            'productType': self.product_type
        }
        resp = self.client.signed_post('/v2/mix/account/set-leverage', body=body)
        return resp

    def adjust_margin(self, symbol: str, margin_amount: float, side: str):
        """
        Adjust isolated margin (add or reduce).
        
        Args:
            symbol: Trading pair
            margin_amount: Amount to adjust
            side: 'add' or 'reduce'
        
        Returns:
            Margin adjustment confirmation
        """
        body = {
            'symbol': symbol,
            'amount': str(margin_amount),
            'type': side,  # 'add' or 'reduce'
            'productType': self.product_type
        }
        resp = self.client.signed_post('/v2/mix/account/add-margin', body=body)
        return resp

    # ---------- market data ----------
    def funding_rate(self, symbol: str):
        """
        Get current funding rate.
        
        Args:
            symbol: Trading pair
        
        Returns:
            {"data": {"fundingRate": "0.0001", ...}, ...}
        """
        params = {
            'symbol': symbol,
            'productType': self.product_type
        }
        resp = self.client.public_get('/v2/mix/market/current-fund-rate', params=params)
        return resp

    def klines(self, symbol: str, interval: str = '15m', limit: int = 120):
        """
        Fetch OHLCV candles.
        
        Args:
            symbol: Trading pair (e.g., "BTC-USDT:USDT")
            interval: Candle interval (1m, 5m, 15m, 30m, 1h, 4h, 1d, etc.)
            limit: Number of candles (default 120)
        
        Returns:
            {"data": [[ts, open, high, low, close, volume], ...], ...}
        """
        params = {
            'symbol': symbol,
            'granularity': interval,
            'limit': limit,
            'productType': self.product_type
        }
        resp = self.client.public_get('/v2/mix/market/candles', params=params)
        return resp

    def ticker(self, symbol: str):
        """
        Get current price and stats.
        
        Args:
            symbol: Trading pair
        
        Returns:
            {"data": {"symbol": "...", "lastPr": "50000", ...}, ...}
        """
        params = {
            'symbol': symbol,
            'productType': self.product_type
        }
        resp = self.client.public_get('/v2/mix/market/ticker', params=params)
        return resp
