#!/usr/bin/env python
"""Test different Bitget API endpoints"""

import requests

endpoints = [
    'https://api.bitget.com/v2/public/time',
    'https://api.bitget.com/v2/spot/public/time',
    'https://api.bitget.com/v2/mix/public/time',
]

print("Testing Bitget API endpoints:")
print("=" * 70)

for url in endpoints:
    try:
        r = requests.get(url, timeout=5, headers={'Accept': 'application/json'})
        status = "✅" if r.status_code == 200 else "❌"
        print(f"{status} {url}")
        print(f"   Status: {r.status_code}")
        if r.status_code == 200:
            try:
                data = r.json()
                print(f"   ✅ Valid JSON response!")
            except:
                print(f"   Response not JSON")
    except Exception as e:
        print(f"❌ {url}")
        print(f"   Error: {str(e)[:50]}")
    print()
