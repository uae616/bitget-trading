# bitget-trading

MT5 integration scaffold for an AI-driven trading agent using the official `MetaTrader5` Python bridge.

## What is implemented

- **MT5 Python bridge integration** via `/home/runner/work/bitget-trading/bitget-trading/mt5_agent/mt5_client.py`
- **Modular architecture**:
  - Market data adapter (`market_data.py`)
  - Decision engine interface (`decision.py`)
  - Execution adapter (`execution.py`)
  - Risk guard (`risk.py`)
  - Trade validator (`validation.py`)
  - Agent orchestrator (`orchestrator.py`)
- **Trade request validation**:
  - Symbol/tradability checks
  - Volume range and step checks
  - Price precision checks
  - SL/TP minimum-distance checks
  - MT5 `order_check` margin/pre-flight check
- **Resilience controls**:
  - Connection health checks
  - Reconnect support
  - Retry policy on execution
  - In-memory idempotency key blocking for duplicate orders
  - Structured audit logging (`audit.log` JSON lines)
- **Staged rollout helpers**:
  - Backtest interface (`simulation.py`)
  - Paper broker placeholder (`simulation.py`)

## Environment variables

Set these before running:

- `MT5_LOGIN`
- `MT5_PASSWORD`
- `MT5_SERVER`
- `MT5_TERMINAL_PATH` (optional)
- `MT5_TIMEOUT_MS` (optional, default `15000`)
- `MAX_DAILY_DRAWDOWN_PCT` (optional, default `5.0`)
- `RISK_PER_TRADE_PCT` (optional, default `1.0`)
- `EXECUTION_MAX_RETRIES` (optional, default `3`)
- `TRADING_START` (optional, default `00:00`)
- `TRADING_END` (optional, default `23:59`)
- `DRY_RUN` (optional, default `false`)
- `PAPER_MODE` (optional, default `true`)
- `AUDIT_LOG_PATH` (optional, default `audit.log`)

## Runtime notes

- Run MT5 terminal on a supported host (commonly Windows x64), logged into your broker.
- Keep one agent process per MT5 terminal instance.
- Do not store credentials in source code; use environment variables or a secrets manager.

## Install and run

```bash
pip install MetaTrader5
python /home/runner/work/bitget-trading/bitget-trading/main.py
```

`main.py` currently wires a `NoopDecisionEngine`; replace it with your model-backed strategy implementation.

## Validation and rollout workflow

1. Feed historical data through `BacktestEngine` for strategy validation.
2. Run forward tests in `PAPER_MODE=true` / demo account.
3. Enable live execution only after risk thresholds and alerting are verified.
