#!/usr/bin/env python3
"""
Test CCXT Bitget integration - connectivity and API access.
"""
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

def test_ccxt_bitget():
    import ccxt
    
    # Load credentials
    api_key = os.getenv('BITGET_API_KEY')
    api_secret = os.getenv('BITGET_API_SECRET')
    api_passphrase = os.getenv('BITGET_API_PASSPHRASE')
    
    if not all([api_key, api_secret, api_passphrase]):
        print("❌ Missing Bitget credentials in .env")
        return False
    
    print("✓ Credentials loaded from .env")
    
    try:
        # Initialize CCXT Bitget exchange
        exchange = ccxt.bitget({
            'apiKey': api_key,
            'secret': api_secret,
            'password': api_passphrase,
            'enableRateLimit': True,
        })
        print("✓ CCXT Bitget exchange initialized")
        
        # Test public endpoint - fetch markets
        try:
            exchange.load_markets()
            print(f"✓ Markets loaded: {len(exchange.symbols)} symbols available")
        except Exception as e:
            print(f"❌ Failed to load markets: {e}")
            return False
        
        # Test public endpoint - fetch ticker
        try:
            ticker = exchange.fetch_ticker('BTC/USDT')
            print(f"✓ BTC/USDT price: ${ticker['last']}")
        except Exception as e:
            print(f"❌ Failed to fetch BTC/USDT ticker: {e}")
            return False
        
        # Test authenticated endpoint - fetch balance
        try:
            balance = exchange.fetch_balance()
            print(f"✓ Account balance fetched")
            print(f"  - Free USDT: {balance.get('USDT', {}).get('free', 0)}")
            print(f"  - Used USDT: {balance.get('USDT', {}).get('used', 0)}")
            print(f"  - Total USDT: {balance.get('USDT', {}).get('total', 0)}")
        except Exception as e:
            print(f"❌ Failed to fetch balance (auth error): {e}")
            return False
        
        # Test open orders endpoint
        try:
            orders = exchange.fetch_open_orders()
            print(f"✓ Open orders fetched: {len(orders)} orders")
        except Exception as e:
            print(f"❌ Failed to fetch open orders: {e}")
            return False
        
        print("\n✅ All CCXT Bitget tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ CCXT initialization failed: {e}")
        return False

if __name__ == '__main__':
    success = test_ccxt_bitget()
    sys.exit(0 if success else 1)
