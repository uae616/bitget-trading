from __future__ import annotations

from .decision import DecisionEngine
from .execution import ExecutionAdapter
from .logging_utils import AuditLogger
from .market_data import MarketDataAdapter
from .risk import RiskGuard
from .types import Signal, TradeRequest, TradeResult
from .validation import TradeRequestValidator


class TradingAgent:
    def __init__(
        self,
        market_data: MarketDataAdapter,
        decision_engine: DecisionEngine,
        risk_guard: RiskGuard,
        validator: TradeRequestValidator,
        execution: ExecutionAdapter,
        audit: AuditLogger,
    ) -> None:
        self.market_data = market_data
        self.decision_engine = decision_engine
        self.risk_guard = risk_guard
        self.validator = validator
        self.execution = execution
        self.audit = audit

    def process_symbol(self, symbol: str, default_volume: float) -> TradeResult | None:
        if not self.risk_guard.within_trading_window():
            return None

        snapshot = self.market_data.get_snapshot(symbol)
        signal = self.decision_engine.decide(snapshot)
        if signal is None:
            return None

        request = _signal_to_request(signal, snapshot.ask if signal.side.lower() == "buy" else snapshot.bid, default_volume)
        self.validator.validate(request)
        result = self.execution.execute(request)

        self.audit.write(
            "agent.decision",
            {
                "symbol": symbol,
                "signal": signal.__dict__,
                "trade_result": result.__dict__,
            },
        )
        return result


def _signal_to_request(signal: Signal, price: float, volume: float) -> TradeRequest:
    return TradeRequest(
        request_id=signal.request_id,
        symbol=signal.symbol,
        side=signal.side,
        volume=volume,
        price=price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
    )
