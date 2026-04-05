#!/usr/bin/env python
"""Real-time monitoring dashboard for MT5 scalper live trading."""
import json
import time
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

def load_state():
    """Load current bot state."""
    state_file = Path('state/mt5_scalper_state.json')
    if not state_file.exists():
        return {}
    with open(state_file) as f:
        return json.load(f)

def analyze_performance(state):
    """Analyze trading performance metrics."""
    activities = state.get('activities', [])
    
    trades = []
    pending_entries = {}
    
    # Reconstruct trades from activities
    for activity in activities:
        action = activity.get('action', '')
        symbol = activity.get('symbol', '')
        ts = activity.get('ts', '')
        price = activity.get('price', 0)
        
        if 'ENTRY' in action:
            direction = action.split('_')[1]  # ENTRY_BUY -> BUY
            pending_entries[symbol] = {
                'direction': direction,
                'entry_price': price,
                'entry_ts': ts,
                'entry_action': action
            }
        elif 'EXIT' in action:
            if symbol in pending_entries:
                trade = pending_entries.pop(symbol)
                trade['exit_price'] = price
                trade['exit_ts'] = ts
                trade['exit_action'] = action
                trades.append(trade)
    
    # Calculate metrics
    closed_trades = [t for t in trades if 'exit_price' in t]
    open_trades = [v for v in pending_entries.values()]
    
    wins = 0
    losses = 0
    total_pnl = 0.0
    
    for trade in closed_trades:
        entry = trade['entry_price']
        exit_price = trade['exit_price']
        direction = trade['direction']
        
        if direction == 'BUY':
            pnl = (exit_price - entry) * 100 if entry > 0 else 0
        else:  # SELL
            pnl = (entry - exit_price) * 100 if entry > 0 else 0
        
        total_pnl += pnl
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1
    
    return {
        'closed_trades': len(closed_trades),
        'open_trades': len(open_trades),
        'total_trades': len(closed_trades) + len(open_trades),
        'wins': wins,
        'losses': losses,
        'win_rate': (wins / len(closed_trades) * 100) if closed_trades else 0,
        'total_pnl': total_pnl,
        'open_positions': open_trades,
        'recent_trades': closed_trades[-10:] if closed_trades else []
    }

def get_signal_stats(state):
    """Get signal generation statistics."""
    activities = state.get('activities', [])
    
    signals = defaultdict(lambda: {'BUY': 0, 'SELL': 0, 'HOLD': 0})
    total_signals = defaultdict(int)
    
    for activity in activities:
        if 'SIGNAL' in activity.get('action', ''):
            symbol = activity.get('symbol', 'UNKNOWN')
            sig_type = activity['action'].split('_')[1]
            signals[symbol][sig_type] += 1
            total_signals[symbol] += 1
    
    return dict(signals), dict(total_signals)

def format_timestamp(ts_str):
    """Format timestamp for display."""
    if not ts_str:
        return 'N/A'
    try:
        return ts_str.split('T')[1].split('+')[0]
    except:
        return ts_str

def clear_screen():
    """Clear terminal screen."""
    import os
    os.system('cls' if sys.platform == 'win32' else 'clear')

def print_dashboard():
    """Print the monitoring dashboard."""
    clear_screen()
    
    state = load_state()
    perf = analyze_performance(state)
    signals, total_sigs = get_signal_stats(state)
    meta = state.get('meta', {})
    positions = state.get('positions', {})
    signal_meta = meta.get('signal_meta', {})
    
    # Header
    print("\n" + "="*90)
    print(" "*25 + "MT5 SCALPER LIVE MONITORING")
    print("="*90)
    
    # Timestamp
    now = datetime.now()
    print(f"\n📊 Dashboard Updated: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔄 Bot Status: {'RUNNING' if meta.get('cycle', 0) > 0 else 'IDLE'}")
    print(f"   Last Cycle: {meta.get('cycle', 'N/A')} | Last Run: {format_timestamp(meta.get('last_run', ''))}")
    
    # Trading Performance
    print("\n" + "-"*90)
    print("📈 TRADING PERFORMANCE")
    print("-"*90)
    print(f"  Closed Trades:  {perf['closed_trades']:3d}")
    print(f"  Open Positions: {perf['open_trades']:3d}")
    print(f"  Total Trades:   {perf['total_trades']:3d}")
    
    if perf['closed_trades'] > 0:
        print(f"  Win Rate:       {perf['win_rate']:5.1f}% ({perf['wins']} wins / {perf['losses']} losses)")
        pnl_color = "✅" if perf['total_pnl'] >= 0 else "❌"
        print(f"  Total P&L:      {pnl_color} {perf['total_pnl']:+.2f} pips")
    else:
        print(f"  Win Rate:       No closed trades yet")
        print(f"  Total P&L:      Pending...")
    
    # Open Positions
    if perf['open_positions']:
        print("\n" + "-"*90)
        print("🎯 OPEN POSITIONS")
        print("-"*90)
        for pos in perf['open_positions']:
            print(f"  {pos.get('symbol', 'N/A'):8s} | {pos.get('direction'):4s} @ {pos.get('entry_price', 0):.2f} | Entry: {format_timestamp(pos.get('entry_ts', ''))}")
    
    # Current Positions (from state)
    if positions:
        print("\n" + "-"*90)
        print("💼 LIVE POSITIONS (from MT5)")
        print("-"*90)
        for symbol, pos in positions.items():
            entry_price = pos.get('entry', 0)
            current = pos.get('current', entry_price)
            pnl = (current - entry_price) if pos.get('direction') == 'BUY' else (entry_price - current)
            print(f"  {symbol:8s} | {pos.get('direction', 'N/A'):4s} @ {entry_price:.2f} → {current:.2f} | P&L: {pnl:+.2f}")
    
    # Signal Statistics
    print("\n" + "-"*90)
    print("📡 SIGNAL GENERATION")
    print("-"*90)
    for symbol in sorted(signals.keys()):
        sig_counts = signals[symbol]
        total = total_sigs[symbol]
        buy_pct = (sig_counts['BUY'] / total * 100) if total > 0 else 0
        sell_pct = (sig_counts['SELL'] / total * 100) if total > 0 else 0
        hold_pct = (sig_counts['HOLD'] / total * 100) if total > 0 else 0
        
        print(f"  {symbol}:")
        print(f"    BUY:  {sig_counts['BUY']:4d} ({buy_pct:5.1f}%)")
        print(f"    SELL: {sig_counts['SELL']:4d} ({sell_pct:5.1f}%)")
        if hold_pct > 0:
            print(f"    HOLD: {sig_counts['HOLD']:4d} ({hold_pct:5.1f}%)")
    
    # Latest Signals
    print("\n" + "-"*90)
    print("⚡ LATEST SIGNALS")
    print("-"*90)
    for symbol, sig in signal_meta.items():
        reason = sig.get('reason', 'N/A')
        direction = sig.get('direction', 'N/A')
        print(f"  {symbol}: {direction:4s} ({reason})")
    
    # Recommendations
    print("\n" + "-"*90)
    print("⚠️  MONITORING CHECKLIST")
    print("-"*90)
    checklist = [
        "✓ Monitor P&L - exit immediately if unexpected losses",
        "✓ Check signal consistency - should alternate BUY/SELL",
        "✓ Verify positions are closing properly",
        "✓ Watch for MT5 disconnections in logs",
        "✓ Confirm stop-loss and take-profit are being hit",
        "✓ Check log file for errors: logs/mt5_scalper.log"
    ]
    for item in checklist:
        print(f"  {item}")
    
    print("\n" + "="*90)
    print("Press Ctrl+C to exit monitoring. Check logs/mt5_scalper.log for detailed activity.")
    print("="*90 + "\n")

def monitor_continuous(refresh_interval=10):
    """Continuously monitor with auto-refresh."""
    try:
        while True:
            print_dashboard()
            print(f"Next refresh in {refresh_interval}s... (press Ctrl+C to exit)\n")
            time.sleep(refresh_interval)
    except KeyboardInterrupt:
        print("\n✅ Monitoring stopped.")
        sys.exit(0)

if __name__ == "__main__":
    refresh = 10
    if len(sys.argv) > 1:
        try:
            refresh = int(sys.argv[1])
        except ValueError:
            print(f"Usage: python monitor_mt5_live.py [refresh_seconds]")
            sys.exit(1)
    
    monitor_continuous(refresh)
