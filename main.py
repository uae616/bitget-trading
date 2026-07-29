from __future__ import annotations

import logging

from mt5_agent import (
    ExecutionAdapter,
    MT5Client,
    MT5Config,
    MarketDataAdapter,
    RiskConfig,
    RiskGuard,
    TradeRequestValidator,
)
from mt5_agent.config import RuntimeConfig
from mt5_agent.decision import DecisionEngine
from mt5_agent.logging_utils import AuditLogger, build_logger
from mt5_agent.orchestrator import TradingAgent
from mt5_agent.types import MarketSnapshot, Signal


class NoopDecisionEngine(DecisionEngine):
    def decide(self, snapshot: MarketSnapshot) -> Signal | None:
        return None


def build_agent() -> TradingAgent:
    mt5_config = MT5Config.from_env()
    risk_config = RiskConfig.from_env()
    runtime = RuntimeConfig.from_env()

    logger = build_logger(level=logging.INFO)
    audit = AuditLogger(runtime.audit_log_path)

    client = MT5Client(mt5_config)
    if not runtime.paper_mode and not client.connect():
        raise RuntimeError("Failed to initialize MT5 terminal connection")

    market_data = MarketDataAdapter(client)
    decision_engine = NoopDecisionEngine()
    risk_guard = RiskGuard(risk_config)
    validator = TradeRequestValidator(client)
    execution = ExecutionAdapter(client, max_retries=risk_config.max_retries, audit_logger=audit)

    logger.info("Trading agent initialized")
    return TradingAgent(market_data, decision_engine, risk_guard, validator, execution, audit)


if __name__ == "__main__":
    build_agent()
