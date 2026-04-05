#!/usr/bin/env python
"""Analyze P&L and unrealized P&L from MT5 scalper dry run."""
import json
from collections import defaultdict

# Load state
with open('state/mt5_scalper_state.json') as f:
    state = json.load(f)

activities = state.get('activities', [])
positions = state.get('positions', {})

print("\n" + "=" * 80)
print("MT5 SCALPER - PROFIT & LOSS ANALYSIS")
print("=" * 80)
print()

# Parse trades
closed_trades = []
entry_prices = {}

for activity in activities:
    action = activity.get('action', '')
    symbol = activity.get('symbol', '')
    message = activity.get('message', '')
    
    # Find entry trades
    if 'ENTRY_' in action:
        direction = action.replace('ENTRY_', '')
        # Parse message for price
        try:
            parts = message.split('price=')
            if len(parts) > 1:
                price_str = parts[1].split(' ')[0]
                price = float(price_str)
                entry_prices[symbol] = {'direction': direction, 'price': price, 'action': action}
        except:
            pass
    
    # Find exit trades
    elif 'EXIT_' in action and symbol in entry_prices:
        entry = entry_prices[symbol]
        # Parse exit message for price and P&L
        if 'TP_HIT' in message or 'SL_HIT' in message:
            try:
                parts = message.split('exit=')
                if len(parts) > 1:
                    exit_str = parts[1].split(' ')[0]
                    exit_price = float(exit_str)
                    
                    # Extract P&L
                    pnl_parts = message.split('pnl=')
                    if len(pnl_parts) > 1:
                        pnl = float(pnl_parts[1])
                    else:
                        pnl = 0
                    
                    exit_type = 'TP' if 'TP_HIT' in message else 'SL'
                    
                    closed_trades.append({
                        'symbol': symbol,
                        'direction': entry['direction'],
                        'entry_price': entry['price'],
                        'exit_price': exit_price,
                        'pnl_pips': pnl,
                        'exit_type': exit_type
                    })
                    del entry_prices[symbol]
            except Exception as e:
                pass

# Calculate stats
print("CLOSED TRADES:")
print("-" * 80)
if closed_trades:
    wins = sum(1 for t in closed_trades if t['pnl_pips'] > 0)
    losses = sum(1 for t in closed_trades if t['pnl_pips'] < 0)
    breakeven = sum(1 for t in closed_trades if t['pnl_pips'] == 0)
    total_pnl = sum(t['pnl_pips'] for t in closed_trades)
    win_rate = wins / len(closed_trades) * 100
    
    print(f"Total Closed Trades:  {len(closed_trades)}")
    print(f"  ✅ Winning:         {wins} ({wins/len(closed_trades)*100:.1f}%)")
    print(f"  ❌ Losing:          {losses} ({losses/len(closed_trades)*100:.1f}%)")
    print(f"  ⚪ Break Even:      {breakeven}")
    print()
    print(f"Realized P&L:         {total_pnl:+.1f} pips")
    print(f"Avg P&L per Trade:    {total_pnl/len(closed_trades):+.2f} pips")
    print(f"Win Rate:             {win_rate:.1f}%")
    print()
    
    # Last 10 trades
    print("Last 10 Closed Trades:")
    print("-" * 80)
    for t in closed_trades[-10:]:
        emoji = "✅ WIN " if t['pnl_pips'] > 0 else "❌ LOSS" if t['pnl_pips'] < 0 else "⚪ EVEN"
        print(f"{emoji}  {t['symbol']:8s} {t['direction']:4s} | "
              f"Entry: {t['entry_price']:8.2f} → Exit: {t['exit_price']:8.2f} | "
              f"P&L: {t['pnl_pips']:+7.2f} pips ({t['exit_type']})")
    print()
else:
    print("❌ NO CLOSED TRADES FOUND")
    print()

print()
print("UNREALIZED P&L (OPEN POSITIONS):")
print("-" * 80)
if positions:
    total_unrealized = 0
    for symbol, pos in positions.items():
        unrealized = pos.get('unrealized_pnl', 0)
        total_unrealized += unrealized
        direction = pos.get('direction', 'N/A')
        entry = pos.get('entry_price', 0)
        current = pos.get('current_price', 0)
        print(f"{symbol:8s} {direction:4s} | "
              f"Entry: {entry:8.2f} → Current: {current:8.2f} | "
              f"Unrealized P&L: {unrealized:+7.2f} pips")
    
    print()
    print(f"Total Unrealized P&L: {total_unrealized:+.1f} pips")
    print(f"Open Positions:       {len(positions)}")
else:
    print("No open positions")
    print()

print()
print("=" * 80)
print("SUMMARY:")
print("=" * 80)
print()

if closed_trades:
    realized_pnl = sum(t['pnl_pips'] for t in closed_trades)
else:
    realized_pnl = 0

if positions:
    unrealized_pnl = sum(p.get('unrealized_pnl', 0) for p in positions.values())
else:
    unrealized_pnl = 0

total_pnl = realized_pnl + unrealized_pnl

print(f"Realized P&L (closed trades):    {realized_pnl:+.1f} pips")
print(f"Unrealized P&L (open positions): {unrealized_pnl:+.1f} pips")
print(f"Total P&L:                       {total_pnl:+.1f} pips")
print()

if closed_trades:
    win_rate = sum(1 for t in closed_trades if t['pnl_pips'] > 0) / len(closed_trades) * 100
    print(f"Win Rate:                        {win_rate:.1f}%")
    print()
    
    if win_rate >= 50:
        print("✅ PROFITABLE - Ready for live trading")
    elif win_rate >= 40:
        print("⚠️  MARGINAL - Proceed with caution")
    else:
        print("❌ LOSING - Needs improvement before live trading")
else:
    print("❌ NO TRADES EXECUTED - Cannot calculate profitability")
    print("   Make sure position entry/exit logic is enabled")

print()
