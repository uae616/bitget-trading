"""
Bitget exchange integration module.

Exports:
- BitgetRestClient: Low-level REST API client
- BitgetSpotAPI: Spot trading API
- BitgetFuturesAPI: Futures trading API
- Data parsing and caching utilities
"""

from .rest_client import BitgetRestClient, BitgetAPIError
from .spot_api import BitgetSpotAPI
from .futures_api import BitgetFuturesAPI
from .data import (
    parse_bitget_exchange_info,
    parse_bitget_ticker,
    parse_bitget_klines,
    parse_bitget_account,
    parse_bitget_order,
    BitgetPriceCache,
    BitgetKlineCache,
)

__all__ = [
    'BitgetRestClient',
    'BitgetAPIError',
    'BitgetSpotAPI',
    'BitgetFuturesAPI',
    'parse_bitget_exchange_info',
    'parse_bitget_ticker',
    'parse_bitget_klines',
    'parse_bitget_account',
    'parse_bitget_order',
    'BitgetPriceCache',
    'BitgetKlineCache',
]
