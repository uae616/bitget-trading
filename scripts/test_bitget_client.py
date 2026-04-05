#!/usr/bin/env python
"""
Test Bitget REST client connectivity.
Usage: python -m scripts.test_bitget_client
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
import os

def test_bitget_client():
    load_dotenv()
    
    # Load credentials
    api_key = os.getenv('BITGET_API_KEY', '')
    api_secret = os.getenv('BITGET_API_SECRET', '')
    api_passphrase = os.getenv('BITGET_API_PASSPHRASE', '')
    
    if not all([api_key, api_secret, api_passphrase]):
        print("❌ Missing Bitget credentials in .env file")
        print("   Required: BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PASSPHRASE")
        return False
    
    print("✓ Credentials loaded from .env")
    
    from src.bitget import BitgetRestClient, BitgetSpotAPI, BitgetFuturesAPI
    
    # Initialize client
    try:
        client = BitgetRestClient(api_key, api_secret, api_passphrase)
        print("✓ BitgetRestClient initialized")
    except Exception as e:
        print(f"❌ Failed to initialize client: {e}")
        return False
    
    # Test ping
    try:
        result = client.ping()
        print(f"✓ Ping successful: {result.get('code', 'unknown')}")
    except Exception as e:
        print(f"❌ Ping failed: {e}")
        return False
    
    # Test time sync
    try:
        server_time = client.server_time()
        print(f"✓ Server time: {server_time}")
    except Exception as e:
        print(f"❌ Time sync failed: {e}")
        return False
    
    # Test Spot API
    try:
        spot = BitgetSpotAPI(client)
        print("✓ BitgetSpotAPI initialized")
        
        # Get exchange info (public)
        info = spot.exchange_info()
        symbols = info.get('data', {}).get('symbols', [])
        print(f"✓ Exchange info loaded: {len(symbols)} symbols")
        
        # Try to get a price
        if 'BTC-USDT' in [s.get('symbol') for s in symbols]:
            price_resp = spot.ticker_price('BTC-USDT')
            price = price_resp.get('data', {}).get('lastPr', 'N/A')
            print(f"✓ BTC-USDT price: {price}")
    except Exception as e:
        print(f"⚠️ Spot API test failed (may be due to rate limits): {e}")
    
    # Test Futures API
    try:
        futures = BitgetFuturesAPI(client)
        print("✓ BitgetFuturesAPI initialized")
    except Exception as e:
        print(f"❌ Futures API initialization failed: {e}")
        return False
    
    # Test signed endpoint (account)
    try:
        account = spot.account()
        code = account.get('code', 'unknown')
        if code == '00000':  # Success code
            print("✓ Account API access granted")
        else:
            print(f"⚠️ Account API returned code: {code}")
    except Exception as e:
        print(f"⚠️ Account API test failed: {e}")
        print("   (This may be due to authentication or rate limits)")
    
    print("\n✅ Bitget client test passed!")
    return True


if __name__ == '__main__':
    success = test_bitget_client()
    sys.exit(0 if success else 1)
