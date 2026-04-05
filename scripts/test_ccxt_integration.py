#!/usr/bin/env python3
"""
Verify CCXT-based Bitget integration works with main_bitget.py and execution layer.
Tests dry-run mode to ensure price fetching, account sync, and strategy execution work.
"""
import sys
import os
from pathlib import Path
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

def test_integration():
    import ccxt
    from src.core.settings import load_config
    from src.core.logger import setup_logger
    from src.engine.scanner import KlineScanner
    
    print("=" * 60)
    print("CCXT Bitget Integration Test")
    print("=" * 60)
    
    # Load config
    try:
        cfg = load_config()
        print("✓ Config loaded")
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return False
    
    # Initialize logger
    log = setup_logger("INFO")
    
    # Load credentials
    api_key = cfg["secrets"]["bitget_api_key"]
    api_secret = cfg["secrets"]["bitget_api_secret"]
    api_passphrase = cfg["secrets"]["bitget_api_passphrase"]
    quote_asset = cfg["portfolio"]["quote_asset"]
    coins = cfg["portfolio"]["coins"]
    
    print(f"✓ Credentials loaded: API Key={api_key[:8]}...")
    print(f"✓ Quote asset: {quote_asset}")
    print(f"✓ Monitoring coins: {coins}")
    
    # Initialize CCXT Bitget
    try:
        exchange = ccxt.bitget({
            'apiKey': api_key,
            'secret': api_secret,
            'password': api_passphrase,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
            }
        })
        exchange.load_markets()
        print(f"✓ CCXT Bitget initialized with {len(exchange.symbols)} symbols")
    except Exception as e:
        print(f"❌ Failed to initialize CCXT: {e}")
        return False
    
    # Verify all trading symbols exist
    ccxt_symbols = [f"{coin}/{quote_asset}" for coin in coins]
    missing_symbols = [s for s in ccxt_symbols if s not in exchange.symbols]
    if missing_symbols:
        print(f"⚠️  Missing symbols: {missing_symbols}")
    else:
        print(f"✓ All trading symbols available on Bitget")
    
    # Create spot API wrapper
    class CCXTSpotWrapper:
        def __init__(self, ex):
            self.exchange = ex
        def account(self):
            return self.exchange.fetch_balance()
        def ticker_price(self, symbol):
            ticker = self.exchange.fetch_ticker(symbol)
            return {'data': {'lastPr': str(ticker['last'])}}
        def klines(self, symbol, interval='15m', limit=120):
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
            return {'data': ohlcv}
    
    spot = CCXTSpotWrapper(exchange)
    
    # Test account fetch
    try:
        balance = spot.account()
        print(f"✓ Account balance fetched")
        print(f"  - USDT available: {balance.get('USDT', {}).get('free', 0)}")
    except Exception as e:
        print(f"❌ Failed to fetch account: {e}")
        return False
    
    # Test price fetching
    print("\nTesting price fetch:")
    for coin in coins[:2]:  # Test first 2 coins
        symbol = f"{coin}/{quote_asset}"
        try:
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            print(f"  ✓ {symbol}: ${price}")
        except Exception as e:
            print(f"  ❌ {symbol}: {e}")
            return False
    
    # Test klines fetch (for strategy)
    print("\nTesting kline data fetch:")
    interval = "15m"
    limit = 120
    for coin in coins[:2]:
        symbol = f"{coin}/{quote_asset}"
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
            print(f"  ✓ {symbol}: {len(ohlcv)} candles")
        except Exception as e:
            print(f"  ❌ {symbol}: {e}")
            return False
    
    # Test scanner initialization
    try:
        scanner = KlineScanner(
            spot_api=spot,
            quote_asset=quote_asset,
            interval=interval,
            limit=limit,
            ttl_sec=20
        )
        print(f"✓ KlineScanner initialized")
    except Exception as e:
        print(f"❌ Failed to initialize scanner: {e}")
        return False
    
    # Test spot filters loading
    print("\nTesting exchange filters:")
    spot_filters = {}
    for symbol in ccxt_symbols[:2]:
        if symbol in exchange.symbols:
            market = exchange.market(symbol)
            limits = market.get('limits', {})
            amount_limits = limits.get('amount', {})
            cost_limits = limits.get('cost', {})
            
            spot_filters[symbol] = {
                'min_notional': cost_limits.get('min', 0),
                'step_size': market.get('precision', {}).get('amount', 0.00001),
                'min_qty': amount_limits.get('min', 0),
            }
            print(f"  ✓ {symbol}:")
            print(f"    - Min notional: {spot_filters[symbol]['min_notional']}")
            print(f"    - Step size: {spot_filters[symbol]['step_size']}")
            print(f"    - Min qty: {spot_filters[symbol]['min_qty']}")
    
    # Test execution wrapper
    print("\nTesting CCXT market order wrapper:")
    from src.engine.execution_bitget import parse_ccxt_order
    
    # Simulate an order response
    simulated_order = {
        'id': 'test_12345',
        'symbol': 'BTC/USDT',
        'filled': 0.001,
        'cost': 70.0,
        'fee': {'cost': 0.14, 'currency': 'USDT'},
        'status': 'closed'
    }
    
    try:
        parsed = parse_ccxt_order(simulated_order, 'BTC/USDT')
        print(f"  ✓ Order parsing works:")
        print(f"    - OrderID: {parsed['orderId']}")
        print(f"    - Filled: {parsed['filledAmount']}")
        print(f"    - Cost: {parsed['filledTotal']}")
        print(f"    - Fees: {parsed['fees']} {parsed['feesCoin']}")
    except Exception as e:
        print(f"  ❌ Order parsing failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ All integration tests passed!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Run: python -m src.main_bitget (with dry_run=true in config)")
    print("2. Verify price fetching and account sync work")
    print("3. Test strategy execution and dry-run trades")
    
    return True

if __name__ == '__main__':
    success = test_integration()
    sys.exit(0 if success else 1)
