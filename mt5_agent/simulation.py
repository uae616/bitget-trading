from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict

from .decision import DecisionEngine
from .types import MarketSnapshot


class BacktestEngine:
    def __init__(self, decision_engine: DecisionEngine) -> None:
        self.decision_engine = decision_engine

    def run(self, snapshots: Iterable[MarketSnapshot]) -> list[dict[str, object]]:
        decisions: list[dict[str, object]] = []
        for snap in snapshots:
            signal = self.decision_engine.decide(snap)
            decisions.append(
                {
                    "timestamp": snap.timestamp,
                    "symbol": snap.symbol,
                    "signal": None if signal is None else asdict(signal),
                }
            )
        return decisions


class PaperBroker:
    def __init__(self) -> None:
        self.orders: list[dict[str, object]] = []

    def place(self, order: dict[str, object]) -> dict[str, object]:
        self.orders.append(order)
        return {"status": "filled", "order": order}
