from __future__ import annotations

from abc import ABC, abstractmethod

from .types import MarketSnapshot, Signal


class DecisionEngine(ABC):
    @abstractmethod
    def decide(self, snapshot: MarketSnapshot) -> Signal | None:
        """Return a trading signal or None when no trade should be placed."""
