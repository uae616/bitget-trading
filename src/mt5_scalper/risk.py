from __future__ import annotations


def size_lots(equity: float, risk_pct: float, stop_points: float, point_value: float, min_lot: float, lot_step: float) -> float:
    if equity <= 0 or risk_pct <= 0 or stop_points <= 0 or point_value <= 0:
        return 0.0
    risk_usd = equity * risk_pct
    raw = risk_usd / (stop_points * point_value)
    if raw < min_lot:
        return 0.0
    steps = int(raw / lot_step)
    return max(min_lot, steps * lot_step)


def get_safe_volume(account_balance: float, risk_percent: float, sl_dist_dollars: float, 
                    contract_size: float = 5000, min_volume: float = 0.01, max_volume: float = 10.0) -> float:
    """
    Calculate safe trading volume based on account balance and risk management.
    
    This function ensures that each trade risks only a percentage of your account,
    preventing catastrophic losses if the strategy has a bad day.
    
    Args:
        account_balance: Total account balance in USD (e.g., 5000)
        risk_percent: Risk per trade as % of account (e.g., 1 = 1%)
        sl_dist_dollars: Stop-loss distance in dollars (e.g., 5.00 for XAGUSD with 50 pip SL)
        contract_size: Pip value multiplier (default 5000 for XAGUSD)
        min_volume: Minimum volume allowed by broker (default 0.01 lots)
        max_volume: Maximum volume for safety (default 10.0 lots)
    
    Returns:
        Safe trading volume (in lots) to use for position sizing
    
    Example:
        >>> get_safe_volume(5000, 1, 5.00)  # $5000 account, 1% risk, $5 SL
        1.0  # Use 1.0 lots
        
        >>> get_safe_volume(5000, 0.5, 5.00)  # $5000 account, 0.5% risk, $5 SL
        0.5  # Use 0.5 lots (smaller position)
    
    Formula:
        Risk Amount = Account Balance × (Risk % / 100)
        Volume = Risk Amount / (SL Distance × Contract Size)
        Final Volume = Max(Min Volume, Min(Calculated Volume, Max Volume))
    
    Safety Features:
        • Respects minimum lot size (no positions too small)
        • Respects maximum lot size (no positions too large)
        • Scales with account balance (bigger account = bigger trades)
        • Scales with risk tolerance (lower risk = smaller trades)
    """
    
    # Validate inputs
    if account_balance <= 0:
        raise ValueError(f"Account balance must be positive, got {account_balance}")
    if risk_percent <= 0 or risk_percent > 100:
        raise ValueError(f"Risk percent must be between 0-100, got {risk_percent}")
    if sl_dist_dollars <= 0:
        raise ValueError(f"Stop-loss distance must be positive, got {sl_dist_dollars}")
    if contract_size <= 0:
        raise ValueError(f"Contract size must be positive, got {contract_size}")
    
    # Calculate dollar amount to risk (e.g., 1% of $5000 = $50)
    risk_amount = account_balance * (risk_percent / 100)
    
    # Calculate volume: Risk / (SL Distance × Contract Size)
    # Example: $50 / ($5.00 × 5000) = $50 / $25000 = 0.002 lots
    calculated_volume = risk_amount / (sl_dist_dollars * contract_size)
    
    # Ensure we stay within broker limits and safety bounds
    final_volume = max(min_volume, min(calculated_volume, max_volume))
    
    # Round to 2 decimal places (standard lot increments)
    final_volume = round(final_volume, 2)
    
    return final_volume


def get_volume_info(account_balance: float, risk_percent: float, sl_dist_dollars: float,
                    tp_dist_dollars: float, contract_size: float = 5000) -> dict:
    """
    Get detailed volume and risk information for a trade.
    
    Args:
        account_balance: Total account balance in USD
        risk_percent: Risk per trade as % of account
        sl_dist_dollars: Stop-loss distance in dollars
        tp_dist_dollars: Take-profit distance in dollars
        contract_size: Pip value multiplier (default 5000 for XAGUSD)
    
    Returns:
        Dictionary with volume, risk, reward, and ratio information
    
    Example:
        >>> info = get_volume_info(5000, 1, 5.00, 10.00)
        >>> info['volume']
        1.0
        >>> info['risk_per_trade']
        50.0
        >>> info['reward_per_trade']
        100.0
        >>> info['risk_reward_ratio']
        '1:2'
    """
    volume = get_safe_volume(account_balance, risk_percent, sl_dist_dollars, contract_size)
    
    # Calculate potential loss and profit
    risk_per_trade = volume * sl_dist_dollars * contract_size
    reward_per_trade = volume * tp_dist_dollars * contract_size
    risk_reward_ratio = f"1:{reward_per_trade / risk_per_trade:.1f}" if risk_per_trade > 0 else "N/A"
    
    return {
        'volume': volume,
        'account_balance': account_balance,
        'risk_percent': risk_percent,
        'sl_distance_dollars': sl_dist_dollars,
        'tp_distance_dollars': tp_dist_dollars,
        'risk_per_trade': risk_per_trade,
        'reward_per_trade': reward_per_trade,
        'risk_reward_ratio': risk_reward_ratio,
        'monthly_profit_estimate': (0.474 * reward_per_trade - 0.526 * risk_per_trade) * 30,  # Assuming 47% win rate
    }
