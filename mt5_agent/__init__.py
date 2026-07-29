"""MT5 AI agent integration package."""

from .config import MT5Config, RiskConfig, RuntimeConfig
from .decision import DecisionEngine
from .execution import ExecutionAdapter
from .market_data import MarketDataAdapter
from .mt5_client import MT5Client
from .orchestrator import TradingAgent
from .risk import RiskGuard
from .types import MarketSnapshot, Signal, TradeRequest, TradeResult
from .validation import TradeRequestValidator

__all__ = [
    "DecisionEngine",
    "ExecutionAdapter",
    "MT5Client",
    "MT5Config",
    "MarketDataAdapter",
    "MarketSnapshot",
    "RiskConfig",
    "RiskGuard",
    "RuntimeConfig",
    "Signal",
    "TradeRequest",
    "TradeRequestValidator",
    "TradeResult",
    "TradingAgent",
]
