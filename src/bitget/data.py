"""
Bitget-specific data parsing and caching utilities.
"""

import time
from typing import Dict, List, Tuple


def parse_bitget_exchange_info(resp: dict) -> dict:
    """
    Parse Bitget exchange info response to extract symbol filters.
    
    Bitget response format:
    {
        "data": {
            "symbols": [
                {
                    "symbol": "BTC-USDT",
                    "baseCoin": "BTC",
                    "quoteCoin": "USDT",
                    "minTradeAmount": "5",  # Min notional in quote
                    "takerFeeRate": "0.002",
                    "makerFeeRate": "0.002",
                    "pricePrecision": "2",
                    "quantityPrecision": "4",
                    ...
                },
                ...
            ]
        },
        "code": "00000",
        ...
    }
    
    Returns:
    {
        "BTC-USDT": {
            "min_notional": 5.0,
            "step_size": 0.0001,
            "min_qty": 0.00001,  # Derived from precision
            "precision": {"price": 2, "qty": 4}
        },
        ...
    }
    """
    out = {}
    symbols = resp.get('data', {}).get('symbols', [])
    
    for s in symbols:
        symbol = s.get('symbol')
        if not symbol:
            continue
        
        min_notional = float(s.get('minTradeAmount', '0') or 0)
        price_precision = int(s.get('pricePrecision', 2) or 2)
        qty_precision = int(s.get('quantityPrecision', 4) or 4)
        
        # Step size is 10^(-quantityPrecision)
        step_size = 10 ** (-qty_precision)
        min_qty = step_size  # Minimum is one step
        
        out[symbol] = {
            'min_notional': min_notional,
            'step_size': step_size,
            'min_qty': min_qty,
            'precision': {
                'price': price_precision,
                'qty': qty_precision
            }
        }
    
    return out


def parse_bitget_ticker(resp: dict) -> float:
    """
    Parse Bitget ticker response to extract price.
    
    Bitget format: {"data": {"lastPr": "50000.50"}, ...}
    
    Returns:
        Price as float
    """
    try:
        return float(resp.get('data', {}).get('lastPr', '0') or 0)
    except (ValueError, TypeError):
        return 0.0


def parse_bitget_klines(resp: dict) -> List[Tuple]:
    """
    Parse Bitget OHLCV candles.
    
    Bitget format: {"data": [[ts, open, high, low, close, volume], ...], ...}
    
    Returns:
        List of [timestamp, open, high, low, close, volume] tuples
    """
    data = resp.get('data', [])
    candles = []
    
    for candle in data:
        if len(candle) >= 6:
            try:
                ts = int(float(candle[0]))
                o = float(candle[1])
                h = float(candle[2])
                l = float(candle[3])
                c = float(candle[4])
                v = float(candle[5])
                candles.append([ts, o, h, l, c, v])
            except (ValueError, TypeError, IndexError):
                continue
    
    return candles


def parse_bitget_account(resp: dict) -> dict:
    """
    Parse Bitget account response to extract balances.
    
    Bitget format:
    {
        "data": {
            "balances": [
                {
                    "coin": "BTC",
                    "available": "1.0",
                    "frozen": "0.0",
                    "locked": "0.0"
                },
                ...
            ]
        },
        ...
    }
    
    Returns:
    {
        "BTC": {"available": 1.0, "frozen": 0.0, "total": 1.0},
        "USDT": {"available": 1000.0, ...},
        ...
    }
    """
    out = {}
    balances = resp.get('data', {}).get('balances', [])
    
    for b in balances:
        coin = b.get('coin')
        if not coin:
            continue
        
        available = float(b.get('available', '0') or 0)
        frozen = float(b.get('frozen', '0') or 0)
        locked = float(b.get('locked', '0') or 0)
        
        out[coin] = {
            'available': available,
            'frozen': frozen,
            'locked': locked,
            'total': available + frozen + locked
        }
    
    return out


def parse_bitget_order(resp: dict) -> dict:
    """
    Parse Bitget spot order response.
    
    Bitget market order response:
    {
        "data": {
            "orderId": "123456",
            "symbol": "BTC-USDT",
            "status": "filled",
            "side": "buy",
            "filledAmount": "1.0",
            "filledTotal": "50000.0",
            "fees": "10.0",  # Fee amount
            "feesCoin": "USDT",
            ...
        },
        ...
    }
    
    Returns:
    {
        "orderId": "123456",
        "symbol": "BTC-USDT",
        "executedQty": "1.0",
        "cummulativeQuoteQty": "50000.0",
        "fills": [
            {
                "price": "50000.0",
                "qty": "1.0",
                "commission": "10.0",
                "commissionAsset": "USDT"
            }
        ],
        "status": "filled"
    }
    """
    data = resp.get('data', {})
    
    filled_amt = float(data.get('filledAmount', '0') or 0)
    filled_total = float(data.get('filledTotal', '0') or 0)
    fees = float(data.get('fees', '0') or 0)
    fees_coin = data.get('feesCoin', 'USDT')
    
    # Calculate average fill price
    fill_price = filled_total / filled_amt if filled_amt > 0 else 0
    
    return {
        'orderId': data.get('orderId'),
        'symbol': data.get('symbol'),
        'executedQty': str(filled_amt),
        'cummulativeQuoteQty': str(filled_total),
        'fills': [
            {
                'price': str(fill_price),
                'qty': str(filled_amt),
                'commission': str(fees),
                'commissionAsset': fees_coin
            }
        ],
        'status': data.get('status', 'unknown')
    }


class BitgetPriceCache:
    """Price cache for Bitget spot symbols."""
    
    def __init__(self, spot_api, ttl_sec: float = 3.0):
        self.spot_api = spot_api
        self.ttl = ttl_sec
        self.cache = {}  # symbol -> (price, expire_ts)

    def get_last_price(self, symbol: str) -> float:
        """Get price for symbol (cached)."""
        now = time.time()
        item = self.cache.get(symbol)
        if item and item[1] > now:
            return item[0]

        resp = self.spot_api.ticker_price(symbol)
        price = parse_bitget_ticker(resp)
        self.cache[symbol] = (price, now + self.ttl)
        return price


class BitgetKlineCache:
    """OHLCV candle cache for Bitget."""
    
    def __init__(self, spot_api):
        self.spot_api = spot_api
        self.cache = {}  # (symbol, interval) -> (candles, fetch_ts)

    def get_klines(self, symbol: str, interval: str = '15m', limit: int = 120) -> List[Tuple]:
        """Fetch OHLCV candles."""
        key = (symbol, interval)
        resp = self.spot_api.klines(symbol, interval, limit)
        candles = parse_bitget_klines(resp)
        if candles:
            self.cache[key] = (candles, time.time())
        return candles

    def last_cached(self, symbol: str, interval: str = '15m') -> List[Tuple]:
        """Get last cached candles without fetching."""
        key = (symbol, interval)
        if key in self.cache:
            return self.cache[key][0]
        return []
