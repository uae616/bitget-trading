#!/usr/bin/env python3
"""
Position Sizing Calculator for MT5 Scalper

This script helps you understand and configure dynamic position sizing
based on your account balance and risk tolerance.

Usage:
    python calculate_position_size.py
"""

from src.mt5_scalper.risk import get_safe_volume, get_volume_info


def print_header(title: str):
    """Print a formatted header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def calculate_and_display(account_balance: float, risk_percent: float, 
                          sl_pips: float = 50, tp_pips: float = 100):
    """Calculate and display position sizing information."""
    
    # For XAGUSD/XAUUSD: 1 pip = 0.10
    contract_size = 5000
    pip_multiplier = 0.10
    sl_dist_dollars = sl_pips * pip_multiplier
    tp_dist_dollars = tp_pips * pip_multiplier
    
    # Get volume info
    info = get_volume_info(account_balance, risk_percent, sl_dist_dollars, tp_dist_dollars, contract_size)
    
    print(f"Account Balance:          ${account_balance:,.2f}")
    print(f"Risk Per Trade:           {risk_percent}% of account")
    print(f"Stop-Loss Distance:       {sl_pips} pips (${sl_dist_dollars:.2f})")
    print(f"Take-Profit Distance:     {tp_pips} pips (${tp_dist_dollars:.2f})")
    print()
    print(f"Recommended Volume:       {info['volume']:.2f} lots")
    print(f"Risk Per Trade:           ${info['risk_per_trade']:.2f}")
    print(f"Reward Per Trade:         ${info['reward_per_trade']:.2f}")
    print(f"Risk/Reward Ratio:        {info['risk_reward_ratio']}")
    print()
    print(f"Expected Monthly Profit*: ${info['monthly_profit_estimate']:,.2f}")
    print(f"  *Based on 47.4% win rate at 30 trades/month")
    print()


def main():
    """Main interactive calculator."""
    
    print_header("MT5 SCALPER - POSITION SIZING CALCULATOR")
    
    print("This tool helps you calculate the safest position size for your account.")
    print("It uses risk-based position sizing to protect your capital.\n")
    
    # Get user inputs
    print("Enter your account information (or press Enter for defaults):\n")
    
    try:
        account_input = input("Account Balance (default $5000): ").strip()
        account_balance = float(account_input) if account_input else 5000.0
    except ValueError:
        account_balance = 5000.0
        print("  → Using default: $5000")
    
    try:
        risk_input = input("Risk Per Trade % (default 1%): ").strip()
        risk_percent = float(risk_input) if risk_input else 1.0
    except ValueError:
        risk_percent = 1.0
        print("  → Using default: 1%")
    
    # Display calculations
    print_header("POSITION SIZING RESULTS")
    
    print("Standard Configuration (50 pip SL, 100 pip TP):")
    print("-" * 80)
    calculate_and_display(account_balance, risk_percent, sl_pips=50, tp_pips=100)
    
    # Show alternative scenarios
    print_header("ALTERNATIVE SCENARIOS")
    
    print("Conservative (0.5% risk):")
    print("-" * 80)
    calculate_and_display(account_balance, 0.5, sl_pips=50, tp_pips=100)
    
    print("Aggressive (2% risk):")
    print("-" * 80)
    calculate_and_display(account_balance, 2.0, sl_pips=50, tp_pips=100)
    
    print("Wider Stops (70 pip SL, 140 pip TP):")
    print("-" * 80)
    calculate_and_display(account_balance, risk_percent, sl_pips=70, tp_pips=140)
    
    # Configuration recommendation
    print_header("CONFIGURATION")
    
    print("To use dynamic position sizing, update your config.toml:\n")
    print(f"[mt5_scalper]")
    print(f"use_dynamic_sizing = true")
    print(f"account_balance = {account_balance}")
    print(f"risk_percent = {risk_percent}")
    print(f"position_size = 0.01  # (fallback if dynamic sizing fails)")
    print()
    
    # Risk management tips
    print_header("RISK MANAGEMENT TIPS")
    
    print("1. START SMALL")
    print("   Begin with dry-run for 1-2 weeks before going live.")
    print()
    
    print("2. USE 1% RISK")
    print("   Risk 1% per trade (not more than 2%) to survive drawdowns.")
    print()
    
    print("3. SCALE GRADUALLY")
    print("   After 4 weeks of profit:")
    print("   • Increase to 1.5% risk")
    print("   • After 8 weeks: increase to 2% risk")
    print()
    
    print("4. DAILY LOSS LIMIT")
    print(f"   If daily loss > ${max(50, account_balance * 0.02):.2f}, STOP trading")
    print()
    
    print("5. WEEKLY REVIEW")
    print("   Check win rate, P&L, and average position hold time.")
    print()
    
    # Formula explanation
    print_header("HOW IT WORKS")
    
    print("Position Size = Risk Amount / (SL Distance × Contract Size)")
    print()
    print("Example with $5,000 account, 1% risk, 50 pip SL:")
    print("  1. Risk Amount = $5,000 × 1% = $50")
    print("  2. SL Distance = 50 pips × 0.10 = $5.00")
    print("  3. Volume = $50 / ($5.00 × 5000) = 0.002 lots")
    print("  4. Rounded = 0.01 lots (minimum)")
    print()
    print("This ensures you never risk more than $50 per trade (1% of $5,000)")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCalculator closed.")
    except Exception as e:
        print(f"\nError: {e}")
        print("Please check your inputs and try again.")
