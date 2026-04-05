#!/usr/bin/env python
"""
Diagnose Bitget API connectivity issues.
Usage: python -m scripts.diagnose_bitget
"""

import sys
import requests
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

def diagnose():
    print("=" * 70)
    print("BITGET API CONNECTIVITY DIAGNOSTIC")
    print("=" * 70)
    print()
    
    # Test 1: Basic connectivity to Bitget domain
    print("1. Testing basic domain connectivity...")
    try:
        r = requests.get('https://www.bitget.com', timeout=5)
        print(f"   ✅ www.bitget.com accessible (status: {r.status_code})")
    except Exception as e:
        print(f"   ❌ www.bitget.com NOT accessible: {e}")
    
    # Test 2: API endpoint without authentication
    print("\n2. Testing API endpoint (public, no auth)...")
    try:
        r = requests.get(
            'https://api.bitget.com/v2/public/time',
            timeout=5,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
            }
        )
        print(f"   Status: {r.status_code}")
        if r.status_code == 403:
            print("   ⚠️ Getting 403 Forbidden - Cloudflare is blocking!")
            print("   This usually means:")
            print("   - Your IP is blocked by Bitget's Cloudflare WAF")
            print("   - You need to whitelist your IP in Bitget API settings")
            print("   - Or Bitget's API may not be accessible from your location")
        elif r.status_code == 200:
            print("   ✅ API accessible!")
            try:
                data = r.json()
                print(f"   Response: {data}")
            except:
                print(f"   Response: {r.text[:100]}")
    except Exception as e:
        print(f"   ❌ API endpoint failed: {e}")
    
    # Test 3: Check IP
    print("\n3. Checking your public IP...")
    try:
        r = requests.get('https://api.ipify.org?format=json', timeout=5)
        data = r.json()
        print(f"   Your public IP: {data.get('ip')}")
        print("   ⚠️ Make sure this IP is whitelisted in Bitget API settings!")
    except Exception as e:
        print(f"   ❌ Could not determine IP: {e}")
    
    # Test 4: VPN/Proxy check
    print("\n4. Testing if VPN/Proxy is needed...")
    print("   If steps 2-3 show API is blocked, try:")
    print("   - Using a VPN (some regions may have restrictions)")
    print("   - Checking Bitget API whitelist in account settings")
    print("   - Contacting Bitget support if IP whitelist is misconfigured")
    
    print("\n" + "=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print("""
If you're getting 403 Forbidden:

1. Log in to Bitget: https://www.bitget.com
2. Go to: Account → API Management
3. Click on your API Key
4. Check "IP Whitelist" section:
   - If it's restricted, add your IP (shown above)
   - Or remove restrictions temporarily for testing
5. Try the test again: python -m scripts.test_bitget_client

If that doesn't work:
- Try with a VPN
- Contact Bitget support
- Check if Bitget API is available in your region
""")

if __name__ == '__main__':
    diagnose()
