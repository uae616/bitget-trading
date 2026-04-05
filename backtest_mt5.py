#!/usr/bin/env python
"""MT5 Scalper Backtesting - Test profitability on historical data."""
import json
from datetime import datetime, timedelta
from collections import defaultdict
import sys

# Try to import MT5
try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    HAS_MT5 = False

from src.core.settings import load_config
from src.core.logger import setup_logger
from src.mt5_scalper.strategy import compute_signal


def get_historical_rates(symbol: str, timeframe: int, num_bars: int = 1000):
    """Get historical OHLC data from MT5."""
    if not HAS_MT5:
        print("ERROR: MetaTrader5 not available for backtesting")
        return None
    
    if not mt5.initialize():
        print(f"ERROR: Failed to initialize MT5: {mt5.last_error()}")
        return None
    
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
    mt5.shutdown()
    
    if rates is None:
        return None
    
    return rates


def get_pip_multiplier(symbol: str) -> float:
    """
    Get pip multiplier based on symbol.
    XAUUSD/XAGUSD: 1 pip = 0.01, but we treat "50 pips" as 5.00 points for reasonable SL.
    For clarity: On Gold, asking for "50 pips" should mean 5.00 units of price movement.
    """
    if symbol in ["XAUUSD", "XAGUSD"]:
        # For metals, 1 pip in our system = 0.10 (not 0.01)
        # So 50 pips = 5.00 price movement
        return 0.10
    else:
        # Default for forex (1 pip = 0.0001)
        return 0.0001


def backtest_strategy(symbol: str, rates: list, sl_pips: float = 50, tp_pips: float = 100, 
                      timeframe: str = "M5", use_signal_filter: bool = True):
    """
    Backtest strategy on historical rates.
    
    Args:
        symbol: Trading symbol (XAUUSD, XAGUSD, etc.)
        rates: Historical OHLC data
        sl_pips: Stop-loss in pips
        tp_pips: Take-profit in pips
        timeframe: M5, M15, H1, etc. (for logging)
        use_signal_filter: Apply trend and cooldown filters to reduce over-trading
    """
    
    if len(rates) < 200:
        print(f"ERROR: Not enough historical data ({len(rates)} bars, need 200+)")
        return None
    
    trades = []
    open_position = None
    signals = []
    last_trade_bar = -100  # Track bars since last trade (for cooldown)
    
    print(f"\n{'='*80}")
    print(f"BACKTESTING {symbol} on {timeframe}")
    print(f"{'='*80}")
    print(f"Historical data: {len(rates)} bars")
    print(f"SL: {sl_pips} pips | TP: {tp_pips} pips")
    print(f"Signal Filter: {'ENABLED (trend + cooldown)' if use_signal_filter else 'DISABLED'}")
    print()
    
    pip_multiplier = get_pip_multiplier(symbol)
    
    # Calculate 200-bar moving average for trend filter
    closes = [float(r["close"]) for r in rates]
    
    # Process each bar
    for i in range(200, len(rates)):
        # Get data up to current bar
        ohlcv = [[int(r["time"]), float(r["open"]), float(r["high"]), float(r["low"]), 
                  float(r["close"]), float(r["tick_volume"])] for r in rates[:i+1]]
        
        bar_time = int(ohlcv[-1][0])
        close_price = float(ohlcv[-1][4])
        high_price = float(ohlcv[-1][2])
        low_price = float(ohlcv[-1][3])
        
        # Check if open position hit TP/SL
        if open_position:
            direction = open_position["direction"]
            entry_price = open_position["entry_price"]
            sl = open_position["sl"]
            tp = open_position["tp"]
            
            # Check SL and TP during the bar (using high/low)
            hit_sl = False
            hit_tp = False
            exit_price = close_price
            
            if direction == "BUY":
                if low_price <= sl:
                    hit_sl = True
                    exit_price = sl
                elif high_price >= tp:
                    hit_tp = True
                    exit_price = tp
            else:  # SELL
                if high_price >= sl:
                    hit_sl = True
                    exit_price = sl
                elif low_price <= tp:
                    hit_tp = True
                    exit_price = tp
            
            if hit_sl or hit_tp:
                # Position closed
                if direction == "BUY":
                    pnl = (exit_price - entry_price) * 100
                else:
                    pnl = (entry_price - exit_price) * 100
                
                exit_type = "TP" if hit_tp else "SL"
                trades.append({
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "direction": direction,
                    "pnl": pnl,
                    "exit_type": exit_type,
                    "bars_held": i - open_position["entry_bar"]
                })
                open_position = None
                last_trade_bar = i
                continue
        
        # Generate signal
        sig = compute_signal(ohlcv, symbol)
        
        # Only process if no open position and signal is not HOLD
        if not open_position and sig.direction != "HOLD":
            # Avoid duplicate signals on same bar
            if signals and signals[-1]["bar_time"] == bar_time and signals[-1]["direction"] == sig.direction:
                continue
            
            # Signal Filter: Reduce over-trading
            skip_signal = False
            if use_signal_filter:
                # 1. Cooldown: Don't trade if we just closed a trade
                bars_since_last_trade = i - last_trade_bar
                if bars_since_last_trade < 5:
                    skip_signal = True
                
                # 2. Trend Filter: Only trade in direction of 200-bar MA
                ma_200 = sum(closes[max(0, i-200):i]) / min(200, i)
                if sig.direction == "BUY" and close_price < ma_200:
                    skip_signal = True
                elif sig.direction == "SELL" and close_price > ma_200:
                    skip_signal = True
            
            if skip_signal:
                continue
            
            # Open position with corrected pip multiplier
            if sig.direction == "BUY":
                sl = close_price - (sl_pips * pip_multiplier)
                tp = close_price + (tp_pips * pip_multiplier)
            else:  # SELL
                sl = close_price + (sl_pips * pip_multiplier)
                tp = close_price - (tp_pips * pip_multiplier)
            
            open_position = {
                "direction": sig.direction,
                "entry_price": close_price,
                "sl": sl,
                "tp": tp,
                "entry_bar": i,
                "entry_time": bar_time
            }
            
            signals.append({
                "bar_time": bar_time,
                "direction": sig.direction,
                "reason": sig.reason,
                "confidence": sig.confidence
            })
    
    return trades, signals, open_position


def calculate_stats(trades: list):
    """Calculate statistics from closed trades."""
    
    if not trades:
        return None
    
    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] < 0)
    breakeven = sum(1 for t in trades if t["pnl"] == 0)
    
    total_pnl = sum(t["pnl"] for t in trades)
    avg_pnl = total_pnl / len(trades)
    max_pnl = max(t["pnl"] for t in trades)
    min_pnl = min(t["pnl"] for t in trades)
    
    win_rate = wins / len(trades) * 100
    loss_rate = losses / len(trades) * 100
    
    avg_bars_held = sum(t["bars_held"] for t in trades) / len(trades)
    
    tp_trades = sum(1 for t in trades if t["exit_type"] == "TP")
    sl_trades = sum(1 for t in trades if t["exit_type"] == "SL")
    
    return {
        "total_trades": len(trades),
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "total_pnl": total_pnl,
        "avg_pnl": avg_pnl,
        "max_pnl": max_pnl,
        "min_pnl": min_pnl,
        "avg_bars_held": avg_bars_held,
        "tp_trades": tp_trades,
        "sl_trades": sl_trades
    }


def print_results(symbol: str, stats: dict, trades: list, signals: list, open_pos):
    """Print backtest results."""
    
    print()
    print("=" * 80)
    print("BACKTEST RESULTS")
    print("=" * 80)
    print()
    
    print(f"Symbol: {symbol}")
    print(f"Total Signals Generated: {len(signals)}")
    print(f"Total Closed Trades: {stats['total_trades']}")
    print()
    
    print("TRADE OUTCOMES:")
    print(f"  ✅ Winning Trades:    {stats['wins']:4d} ({stats['win_rate']:5.1f}%)")
    print(f"  ❌ Losing Trades:     {stats['losses']:4d} ({stats['loss_rate']:5.1f}%)")
    print(f"  ⚪ Break Even:        {stats['breakeven']:4d}")
    print()
    
    print("P&L METRICS:")
    print(f"  Total P&L:            {stats['total_pnl']:+.1f} pips")
    print(f"  Avg P&L per Trade:    {stats['avg_pnl']:+.2f} pips")
    print(f"  Max Win:              {stats['max_pnl']:+.1f} pips")
    print(f"  Max Loss:             {stats['min_pnl']:+.1f} pips")
    print()
    
    print("EXIT ANALYSIS:")
    print(f"  Closed at TP:         {stats['tp_trades']:4d} trades")
    print(f"  Closed at SL:         {stats['sl_trades']:4d} trades")
    print(f"  Avg Bars Held:        {stats['avg_bars_held']:.1f} bars")
    print()
    
    print("LAST 10 TRADES:")
    print("-" * 80)
    for trade in trades[-10:]:
        emoji = "✅ WIN " if trade["pnl"] > 0 else "❌ LOSS" if trade["pnl"] < 0 else "⚪ EVEN"
        print(f"{emoji}  {trade['direction']:4s} | "
              f"Entry: {trade['entry_price']:8.2f} → Exit: {trade['exit_price']:8.2f} | "
              f"P&L: {trade['pnl']:+7.2f} pips ({trade['exit_type']})")
    print()
    
    print("=" * 80)
    print("VERDICT:")
    print("=" * 80)
    print()
    
    if stats['win_rate'] >= 55:
        verdict = "✅ STRONG PROFITABLE"
        action = "Ready for live trading"
        color = "\033[92m"  # Green
    elif stats['win_rate'] >= 50:
        verdict = "✅ PROFITABLE"
        action = "Safe to go live with caution"
        color = "\033[92m"  # Green
    elif stats['win_rate'] >= 45:
        verdict = "⚠️  MARGINAL"
        action = "Proceed with small position size"
        color = "\033[93m"  # Yellow
    elif stats['win_rate'] >= 40:
        verdict = "⚠️  WEAK"
        action = "Monitor closely, consider fixing"
        color = "\033[93m"  # Yellow
    else:
        verdict = "❌ LOSING"
        action = "FIX STRATEGY before going live"
        color = "\033[91m"  # Red
    
    print(f"Win Rate: {stats['win_rate']:.1f}%")
    print(f"Status:   {verdict}")
    print(f"Action:   {action}")
    print()
    
    if open_pos:
        print(f"⚠️  One position still open at end of backtest")
        print(f"   {open_pos['direction']} @ {open_pos['entry_price']:.2f}")
    
    print()


def main():
    """Run backtest."""
    
    if not HAS_MT5:
        print("ERROR: This backtesting tool requires MetaTrader5 to be installed")
        print("Install with: pip install MetaTrader5")
        sys.exit(1)
    
    cfg = load_config()
    scalper_cfg = cfg.get("mt5_scalper", {})
    
    symbols = [str(s).upper() for s in scalper_cfg.get("symbols", ["XAUUSD", "XAGUSD"])]
    sl_pips = float(scalper_cfg.get("stop_loss_pips", 50))  # Updated default
    tp_pips = float(scalper_cfg.get("take_profit_pips", 100))  # Updated default
    
    print("\n" + "=" * 80)
    print("MT5 SCALPER BACKTEST (WITH PIP FIX & SIGNAL FILTERING)")
    print("=" * 80)
    print()
    print("Improvements:")
    print("  ✅ Fixed pip calculation (now accounts for decimal places)")
    print("  ✅ Added signal filtering (trend + cooldown)")
    print("  ✅ Higher timeframe test (M15 instead of M5)")
    print()
    print("Fetching historical data from MT5...")
    print()
    
    all_stats = {}
    
    for symbol in symbols:
        # Test on M15 timeframe (15-minute candles) instead of M5
        # This reduces over-trading significantly
        print(f"\n--- Testing {symbol} on M15 timeframe ---")
        rates = get_historical_rates(symbol, mt5.TIMEFRAME_M15, 5000)
        
        if rates is None:
            print(f"⚠️  Could not fetch data for {symbol}")
            continue
        
        # Run backtest with signal filtering enabled
        trades, signals, open_pos = backtest_strategy(
            symbol, rates, sl_pips, tp_pips, 
            timeframe="M15", use_signal_filter=True
        )
        
        if trades:
            stats = calculate_stats(trades)
            all_stats[symbol] = stats
            print_results(symbol, stats, trades, signals, open_pos)
        else:
            print(f"No trades generated for {symbol}")
    
    # Summary for all symbols
    if all_stats:
        print("\n" + "=" * 80)
        print("OVERALL SUMMARY")
        print("=" * 80)
        print()
        
        total_trades = sum(s["total_trades"] for s in all_stats.values())
        total_wins = sum(s["wins"] for s in all_stats.values())
        total_pnl = sum(s["total_pnl"] for s in all_stats.values())
        overall_win_rate = total_wins / total_trades * 100 if total_trades > 0 else 0
        
        print(f"Total Trades (All Symbols): {total_trades}")
        print(f"Total Wins:                 {total_wins} ({overall_win_rate:.1f}%)")
        print(f"Total P&L:                  {total_pnl:+.1f} pips")
        print()
        
        for symbol, stats in all_stats.items():
            print(f"{symbol}: {stats['total_trades']} trades | "
                  f"Win Rate: {stats['win_rate']:.1f}% | "
                  f"P&L: {stats['total_pnl']:+.1f} pips")
        
        print()
        if overall_win_rate >= 45:
            print("✅ BACKTEST PROFITABLE - Strategy is viable")
        else:
            print("❌ BACKTEST NOT PROFITABLE - Needs improvement")


if __name__ == "__main__":
    main()
