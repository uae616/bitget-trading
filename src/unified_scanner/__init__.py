"""Unified Signal Scanner — self-contained package."""
from .indicators import *  # noqa: F401,F403
from .signal_scorer import score_signal, SignalResult  # noqa: F401
from .sl_tp import compute_sl_tp, SlTpResult  # noqa: F401
from .backtest import run_backtest, backtest_summary, BacktestResult  # noqa: F401
