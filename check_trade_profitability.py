#!/usr/bin/env python
"""Check if the dry run trades were profitable or losing."""
import json
from collections import defaultdict

# Load state
with open('state/mt5_scalper_state.json') as f:
    state = json.load(f)

activities = state.get('activities', [])

# Count activity types
action_types = defaultdict(int)
for activity in activities:
    action = activity.get('action', '')
    action_types[action] += 1

print("=" * 75)
print("DRY RUN ANALYSIS - PROFITABILITY CHECK")
print("=" * 75)
print()
print("ACTIVITY BREAKDOWN:")
print("-" * 75)
for action, count in sorted(action_types.items()):
    print(f"  {action:20s}: {count:5d}")

print()
print("=" * 75)
print()

# Track closed trades
trades = []
pending = {}

for activity in activities:
    action = activity.get('action', '')
    symbol = activity.get('symbol', '')
    price = activity.get('price', 0)
    ts = activity.get('ts', '')
    
    if 'ENTRY' in action:
        direction = action.replace('ENTRY_', '')
        pending[symbol] = {
            'direction': direction,
            'entry_price': price,
            'entry_ts': ts
        }
    elif 'EXIT' in action and symbol in pending:
        entry = pending.pop(symbol)
        exit_price = price
        direction = entry['direction']
        
        # Calculate P&L in pips (1 pip = 0.01 move)
        if direction == 'BUY':
            pnl = (exit_price - entry['entry_price']) * 100
        else:  # SELL
            pnl = (entry['entry_price'] - exit_price) * 100
        
        trades.append({
            'symbol': symbol,
            'direction': direction,
            'entry': entry['entry_price'],
            'exit': exit_price,
            'pnl': pnl
        })

print("CLOSED TRADES ANALYSIS:")
print("-" * 75)
print()

if trades:
    wins = sum(1 for t in trades if t['pnl'] > 0)
    losses = sum(1 for t in trades if t['pnl'] < 0)
    breakeven = sum(1 for t in trades if t['pnl'] == 0)
    total_pnl = sum(t['pnl'] for t in trades)
    win_rate = wins / len(trades) * 100 if trades else 0
    loss_rate = losses / len(trades) * 100 if trades else 0
    avg_pnl = total_pnl / len(trades)
    
    print(f"Total Closed Trades:  {len(trades)}")
    print(f"  ✅ Winning Trades:  {wins:4d} ({wins/len(trades)*100:5.1f}%)")
    print(f"  ❌ Losing Trades:   {losses:4d} ({losses/len(trades)*100:5.1f}%)")
    print(f"  ⚪ Break Even:      {breakeven:4d}")
    print()
    print(f"Total P&L:            {total_pnl:+.1f} pips")
    print(f"Avg P&L per Trade:    {avg_pnl:+.2f} pips")
    print(f"Win Rate:             {win_rate:.1f}%")
    print(f"Loss Rate:            {loss_rate:.1f}%")
    print()
    
    # Profitability verdict
    print("PROFITABILITY VERDICT:")
    print("-" * 75)
    if win_rate >= 55:
        print(f"✅ STRONG PROFITABLE - {win_rate:.1f}% win rate is EXCELLENT")
        print("   Strategy is making more money than losing")
    elif win_rate >= 50:
        print(f"✅ PROFITABLE - {win_rate:.1f}% win rate is GOOD")
        print("   Strategy breaks even or slightly profitable")
    elif win_rate >= 45:
        print(f"⚠️  MARGINAL - {win_rate:.1f}% win rate is ACCEPTABLE")
        print("   Strategy barely profitable, needs improvement")
    elif win_rate >= 40:
        print(f"⚠️  WEAK - {win_rate:.1f}% win rate needs work")
        print("   90% loss rate means strategy LOSES MONEY")
    else:
        print(f"❌ LOSING - {win_rate:.1f}% win rate is BAD")
        print("   Strategy LOSES MONEY - DO NOT trade live")
    
    print()
    print("RECOMMENDATION:")
    print("-" * 75)
    if win_rate >= 45:
        print("✅ OK to proceed to live trading with caution")
        print("   But monitor closely and be ready to stop if losses continue")
    else:
        print("❌ DO NOT proceed to live trading")
        print("   Strategy needs to be fixed or improved first")
    
    print()
    print("=" * 75)
    print("LAST 15 TRADES (Most Recent):")
    print("=" * 75)
    print()
    for t in trades[-15:]:
        emoji = "✅ WIN " if t['pnl'] > 0 else "❌ LOSS" if t['pnl'] < 0 else "⚪ EVEN"
        print(f"{emoji}  {t['symbol']:8s} {t['direction']:4s} | Entry: {t['entry']:8.2f} → Exit: {t['exit']:8.2f} | PnL: {t['pnl']:+7.2f} pips")
    
else:
    print("❌ NO CLOSED TRADES FOUND IN DRY RUN")
    print()
    print("This means:")
    print("  • Signals were generated (261 total)")
    print("  • But NO trades were executed or closed")
    print("  • Strategy might not have:")
    print("    - Entry logic implemented")
    print("    - Exit logic implemented")
    print("    - Proper position management")
    print()
    print("Current open/pending positions:")
    print(f"  {len(pending)} positions still open")
    if pending:
        for symbol, trade in pending.items():
            print(f"    • {symbol}: {trade['direction']} @ {trade['entry_price']}")

print()
