#!/usr/bin/env python
"""Test if CCXT supports Bitget"""

try:
    import ccxt
    print("✓ CCXT loaded")
    
    # Check if bitget is available
    if 'bitget' in ccxt.exchanges:
        print("✓ Bitget IS supported in CCXT!")
        print("\nYou can use CCXT for Bitget instead of our REST client.")
        print("CCXT handles all the API complexity automatically.")
    else:
        print("❌ Bitget not found in CCXT")
        print("\nAvailable exchanges with 'bit' in name:")
        for e in sorted(ccxt.exchanges):
            if 'bit' in e.lower():
                print(f"  - {e}")
except Exception as e:
    print(f"❌ Error: {e}")
