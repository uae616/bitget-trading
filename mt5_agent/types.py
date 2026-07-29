from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .constants import DEFAULT_DEVIATION_POINTS, DEFAULT_MAGIC_NUMBER


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    bid: float
    ask: float
    spread: float
    timestamp: datetime
    features: dict[str, Any]


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: str
    confidence: float
    request_id: str
    stop_loss: float | None = None
    take_profit: float | None = None
    note: str | None = None


@dataclass(frozen=True)
class TradeRequest:
    request_id: str
    symbol: str
    side: str
    volume: float
    price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    deviation: int = DEFAULT_DEVIATION_POINTS
    magic: int = DEFAULT_MAGIC_NUMBER
    comment: str = "ai-agent"


@dataclass(frozen=True)
class TradeResult:
    request_id: str
    accepted: bool
    code: int
    message: str
    order_id: int | None = None
