#!/usr/bin/env python
"""
Debug Bitget API requests to diagnose 403 error
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
import requests
import hmac
import hashlib
import base64
import time
import json

load_dotenv()

api_key = os.getenv('BITGET_API_KEY', '')
api_secret = os.getenv('BITGET_API_SECRET', '')
api_passphrase = os.getenv('BITGET_API_PASSPHRASE', '')

print("=" * 70)
print("BITGET API DEBUG")
print("=" * 70)
print()

# Check credentials loaded
if not all([api_key, api_secret, api_passphrase]):
    print("❌ Missing credentials!")
    sys.exit(1)

print(f"✓ API Key: {api_key[:10]}...")
print(f"✓ API Secret: {api_secret[:10]}...")
print(f"✓ Passphrase: {api_passphrase[:10]}...")
print()

# Test 1: Simple public endpoint
print("TEST 1: Public endpoint (unsigned)")
print("-" * 70)
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'Accept-Encoding': 'gzip, deflate',
})

url = 'https://api.bitget.com/v2/public/time'
print(f"URL: {url}")
print(f"Method: GET")
print(f"Headers: {dict(session.headers)}")
print()

try:
    r = session.get(url, timeout=10)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        try:
            data = r.json()
            print(f"Response: {data}")
            print("✅ Public endpoint works!")
        except Exception as e:
            print(f"Error parsing response: {e}")
    else:
        print(f"Error status: {r.status_code}")
        print(f"Response length: {len(r.content)} bytes")
        try:
            # Try to decompress
            import gzip
            decompressed = gzip.decompress(r.content).decode('utf-8')
            print(f"Decompressed: {decompressed[:200]}")
        except:
            print(f"Could not decompress response")
except Exception as e:
    print(f"❌ Request failed: {e}")

print()
print()

# Test 2: Signed request to /v2/mix/account/accounts (Futures account)
print("TEST 2: Signed endpoint (Futures account)")
print("-" * 70)

timestamp_ms = str(int(time.time() * 1000))
method = 'GET'
path = '/v2/mix/account/accounts'
params = {'productType': 'umcbl'}

# Build query string
query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
full_path = f"{path}?{query_string}"

# Build message for signature
message = timestamp_ms + method + full_path + ''

# Calculate signature
signature = base64.b64encode(
    hmac.new(
        api_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
).decode('utf-8')

print(f"Timestamp: {timestamp_ms}")
print(f"Message: {message}")
print(f"Signature: {signature[:20]}...")
print()

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'Accept-Encoding': 'gzip, deflate',
    'Content-Type': 'application/json',
    'X-BITGET-APIKEY': api_key,
    'X-BITGET-SIGN': signature,
    'X-BITGET-TIMESTAMP': timestamp_ms,
    'X-BITGET-PASSPHRASE': api_passphrase,
}

url_full = f'https://api.bitget.com{full_path}'
print(f"URL: {url_full}")
print(f"Method: {method}")
print(f"Headers:")
for k, v in headers.items():
    val = v[:20] + '...' if len(v) > 20 else v
    print(f"  {k}: {val}")
print()

try:
    r = session.get(url_full, headers=headers, timeout=10)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        try:
            data = r.json()
            print(f"Response: {json.dumps(data, indent=2)[:300]}")
            print("✅ Signed request works!")
        except Exception as e:
            print(f"Error parsing response: {e}")
    else:
        print(f"Error status: {r.status_code}")
        print(f"Response content length: {len(r.content)} bytes")
        try:
            # Try to decompress if gzipped
            import gzip
            decompressed = gzip.decompress(r.content).decode('utf-8')
            print(f"Response (decompressed): {decompressed[:300]}")
        except:
            try:
                # Try as plain text
                text = r.text
                print(f"Response (text): {text[:300]}")
            except:
                print(f"Could not decompress or decode response")
except Exception as e:
    print(f"❌ Request failed: {e}")

print()
print("=" * 70)
print("If both tests show 403:")
print("1. Check IP whitelist in Bitget API settings")
print("2. Check API key permissions (need Spot + Futures)")
print("3. Check passphrase is correct (case-sensitive)")
print("=" * 70)
