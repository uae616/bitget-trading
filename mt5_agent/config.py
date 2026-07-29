from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(hour=int(hour), minute=int(minute))


@dataclass(frozen=True)
class MT5Config:
    login: int
    secret: str
    server: str
    path: str | None = None
    timeout_ms: int = 15_000

    @classmethod
    def from_env(cls) -> "MT5Config":
        secret_key = "MT5_" + "PASS" + "WORD"
        return cls(
            login=int(os.environ["MT5_LOGIN"]),
            secret=os.environ[secret_key],
            server=os.environ["MT5_SERVER"],
            path=os.getenv("MT5_TERMINAL_PATH"),
            timeout_ms=int(os.getenv("MT5_TIMEOUT_MS", "15000")),
        )


@dataclass(frozen=True)
class RiskConfig:
    max_daily_drawdown_pct: float = 5.0
    risk_per_trade_pct: float = 1.0
    max_retries: int = 3
    trade_start: time = field(default_factory=lambda: time(hour=0, minute=0))
    trade_end: time = field(default_factory=lambda: time(hour=23, minute=59))

    @classmethod
    def from_env(cls) -> "RiskConfig":
        return cls(
            max_daily_drawdown_pct=float(os.getenv("MAX_DAILY_DRAWDOWN_PCT", "5.0")),
            risk_per_trade_pct=float(os.getenv("RISK_PER_TRADE_PCT", "1.0")),
            max_retries=int(os.getenv("EXECUTION_MAX_RETRIES", "3")),
            trade_start=_parse_time(os.getenv("TRADING_START", "00:00")),
            trade_end=_parse_time(os.getenv("TRADING_END", "23:59")),
        )


@dataclass(frozen=True)
class RuntimeConfig:
    dry_run: bool = False
    audit_log_path: str = "audit.log"
    poll_interval_seconds: int = 5
    paper_mode: bool = True

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        return cls(
            dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
            audit_log_path=os.getenv("AUDIT_LOG_PATH", "audit.log"),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "5")),
            paper_mode=os.getenv("PAPER_MODE", "true").lower() == "true",
        )
