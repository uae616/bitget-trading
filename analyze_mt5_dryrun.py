#!/usr/bin/env python
"""Analyze MT5 scalper dry run results."""
import json
import sys
from collections import defaultdict

def analyze_dryrun():
    # Load state
    with open('state/mt5_scalper_state.json') as f:
        state = json.load(f)
    
    # Extract activities
    activities = state.get('activities', [])
    
    print("\n" + "="*70)
    print("MT5 SCALPER DRY RUN ANALYSIS")
    print("="*70)
    
    # Count signals by type
    signal_counts = defaultdict(int)
    signal_by_symbol = defaultdict(lambda: defaultdict(int))
    
    for activity in activities:
        action = activity.get('action', '')
        symbol = activity.get('symbol', 'UNKNOWN')
        
        if 'SIGNAL' in action:
            signal_type = action.split('_')[1]  # SIGNAL_BUY -> BUY
            signal_counts[signal_type] += 1
            signal_by_symbol[symbol][signal_type] += 1
    
    # Print summary
    total_signals = sum(signal_counts.values())
    print(f"\nTotal Signals Generated: {total_signals}")
    
    if total_signals > 0:
        print("\nSignal Breakdown:")
        for sig_type, count in sorted(signal_counts.items()):
            pct = (count / total_signals) * 100
            print(f"  {sig_type:6s}: {count:4d} ({pct:5.1f}%)")
        
        print("\nSignals by Symbol:")
        for symbol in sorted(signal_by_symbol.keys()):
            sigs = signal_by_symbol[symbol]
            total = sum(sigs.values())
            print(f"  {symbol}:")
            for sig_type, count in sorted(sigs.items()):
                pct = (count / total) * 100
                print(f"    {sig_type}: {count} ({pct:.1f}%)")
    
    # Bot status
    meta = state.get('meta', {})
    print(f"\nBot Status:")
    print(f"  Last Cycle: {meta.get('cycle', 'N/A')}")
    print(f"  Last Run: {meta.get('last_run', 'N/A')}")
    
    # Current positions
    positions = state.get('positions', {})
    print(f"\nCurrent Positions: {len(positions)}")
    for symbol, pos in positions.items():
        print(f"  {symbol}: {pos.get('direction', 'N/A')} @ {pos.get('entry', 'N/A')}")
    
    # Latest signals
    signal_meta = meta.get('signal_meta', {})
    print(f"\nLatest Signals:")
    for symbol, sig in signal_meta.items():
        print(f"  {symbol}: {sig.get('direction')} ({sig.get('reason')})")
    
    print("\n" + "="*70)
    print("RECOMMENDATIONS BEFORE GOING LIVE:")
    print("="*70)
    print("""
1. SIGNAL QUALITY:
   - Check if signal distribution looks balanced (not all BUY/SELL)
   - Confidence scores should be >0.5 for reliable trades
   
2. POSITION MANAGEMENT:
   - Verify position sizing is configured correctly
   - Check stop-loss and take-profit levels are appropriate
   
3. ACCOUNT SETUP:
   - Ensure MT5 terminal is running and connected
   - Verify account credentials in .env are correct
   - Test with micro lot sizes first
   
4. CONFIGURATION:
   - Review config.toml and .env settings
   - Verify symbols are correctly configured for your account
   - Check cycle_seconds and timeframe match your trading style
   
5. BACKTEST HISTORY:
   - Run dry mode for 24+ hours to gather data
   - Check success rate of signals against live prices
   - Monitor for signal consistency and strategy drift
   
6. SAFETY:
   - Keep dry_run=true until confident
   - Use small position sizes for initial live trades
   - Monitor log files during live trading
   - Have stop-loss on all positions
    """)

if __name__ == "__main__":
    try:
        analyze_dryrun()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
