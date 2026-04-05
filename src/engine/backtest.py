"""
Signal backtesting engine.

Ported from:
- signal_engine.py              (backtest loop over historical candles)
- signal_engine_simulation.py   (trade pair simulation, income tracking)
- dual_strategy_with_RSI.py     (strategy stats, win rate, drawdown)

Runs the unified signal scorer over historical klines and tracks performance.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.engine.signal_scorer import score_signal, SignalResult


@dataclass
class BacktestTrade:
    bar_index: int
    direction: str
    entry_price: float
    exit_price: float
    pnl: float
    score: int
    reasons: list[str] = field(default_factory=list)


@dataclass
class BacktestResult:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    max_drawdown: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    trades: list[BacktestTrade] = field(default_factory=list)


def run_backtest(
    klines: list,
    scanner_cfg: dict | None = None,
    hold_bars: int = 6,
    trade_fee: float = 0.001,
    min_bars: int = 50,
) -> BacktestResult:
    """
    Backtest the unified signal scorer on historical klines.

    For each bar (starting from `min_bars`), the scorer runs on all data up
    to that bar. If a BUY or SELL signal fires, a simulated trade is opened
    and closed `hold_bars` later (or at RSI exit).

    Args:
        klines: full OHLCV list
        scanner_cfg: scorer config dict
        hold_bars: how many bars to hold a position (default 6)
        trade_fee: fee per side (default 0.1%)
        min_bars: minimum bars before first signal check
    """
    cfg = scanner_cfg or {}
    result = BacktestResult()
    equity_peak = 0.0
    equity = 0.0

    total_bars = len(klines)
    if total_bars < min_bars + hold_bars:
        return result

    i = min_bars
    while i < total_bars - hold_bars:
        # Score on data up to bar i
        window = klines[:i + 1]
        sig: SignalResult = score_signal(window, cfg)

        if sig.direction == "HOLD":
            i += 1
            continue

        entry_price = float(klines[i][4])
        exit_price = float(klines[i + hold_bars][4])

        if entry_price <= 0:
            i += 1
            continue

        # Calculate PnL
        if sig.direction == "BUY":
            pnl = (exit_price / entry_price - 1) - 2 * trade_fee
        else:  # SELL
            pnl = (1 - exit_price / entry_price) - 2 * trade_fee

        trade = BacktestTrade(
            bar_index=i,
            direction=sig.direction,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            score=sig.score,
            reasons=sig.reasons,
        )
        result.trades.append(trade)

        equity += pnl
        if equity > equity_peak:
            equity_peak = equity
        drawdown = equity_peak - equity
        if drawdown > result.max_drawdown:
            result.max_drawdown = drawdown

        if pnl > result.best_trade:
            result.best_trade = pnl
        if pnl < result.worst_trade:
            result.worst_trade = pnl

        # Skip ahead past the hold period to avoid overlapping trades
        i += hold_bars

    # Aggregate stats
    result.total_trades = len(result.trades)
    if result.total_trades > 0:
        result.wins = sum(1 for t in result.trades if t.pnl > 0)
        result.losses = result.total_trades - result.wins
        result.win_rate = result.wins / result.total_trades
        result.total_pnl = sum(t.pnl for t in result.trades)
        result.avg_pnl = result.total_pnl / result.total_trades

    return result


def backtest_summary(bt: BacktestResult) -> str:
    """Format backtest result as a human-readable string."""
    lines = [
        f"Trades: {bt.total_trades}  |  Wins: {bt.wins}  |  Losses: {bt.losses}",
        f"Win Rate: {bt.win_rate * 100:.1f}%",
        f"Total PnL: {bt.total_pnl * 100:.2f}%",
        f"Avg PnL/trade: {bt.avg_pnl * 100:.3f}%",
        f"Max Drawdown: {bt.max_drawdown * 100:.2f}%",
        f"Best Trade: {bt.best_trade * 100:.3f}%",
        f"Worst Trade: {bt.worst_trade * 100:.3f}%",
    ]
    return "\n".join(lines)
