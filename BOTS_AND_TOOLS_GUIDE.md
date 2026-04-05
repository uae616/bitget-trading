# Bots and Tools Guide

This file is the single map of what each bot does and how to run it.

## 1) Main bot families

### A. Bitget spot rebalance bot
- Entry: `src/main_bitget.py`
- Run: `./scripts/run_bitget_bot.ps1`
- Hub run: `./scripts/bot_hub.ps1 -Target bitget-spot`
- Purpose: Spot rebalance logic with strategy and execution via CCXT Bitget.

### B. Futures bot
- Entry: `src/main_futures.py`
- Run: `./scripts/run_futures_bot.ps1`
- Status: `./scripts/status_futures_bot.ps1`
- Hub run: `./scripts/bot_hub.ps1 -Target futures`
- Purpose: Futures bot flow under `src/futures/` with risk controls.

### C. Legacy Binance bot
- Entry: `src/main.py`
- Run: `./scripts/run_bot.ps1`
- Status: `./scripts/status_bot.ps1`
- Stop: `./scripts/stop_bot.ps1`
- Purpose: Older Binance path kept for backward compatibility.

## 2) Scanner and signal tools

### A. Unified scanner (exchange scanner)
- Entry: `src/unified_scanner/main.py`
- Hub run: `./scripts/bot_hub.ps1 -Target scanner -ExtraArgs @('--exchange','bitget','--top','20')`
- Supports: debug, watch mode, backtest flag, JSON output.

### B. Unified scanner dashboard
- Entry: `src/unified_scanner/dashboard.py`
- Run: `./scripts/start_unified_monitor.ps1`
- Hub run: `./scripts/bot_hub.ps1 -Target dashboard`

### C. MT5 selective scanner
- Entry: `src/mt5_scanner/main.py`
- Hub run: `./scripts/bot_hub.ps1 -Target mt5-scanner`
- Example: `./scripts/bot_hub.ps1 -Target mt5-scanner -ExtraArgs @('XAUUSD','XAGUSD','--debug')`

## 3) MT5 strategy bot and validation

### A. MT5 scalper bot
- Entry: `src/mt5_scalper/main.py`
- Hub run: `./scripts/bot_hub.ps1 -Target mt5-scalper`

### B. MT5 dry-run analysis
- Tool: `analyze_mt5_dryrun.py`
- Hub run: `./scripts/bot_hub.ps1 -Target analyze-mt5-dryrun`

### C. MT5 backtest
- Tool: `backtest_mt5.py`
- Hub run: `./scripts/bot_hub.ps1 -Target backtest-mt5`

### D. MT5 live transition helper
- Script: `scripts/transition_mt5.ps1`
- Purpose: guided move from dry-run to live with checks and safeguards.

## 4) Bitget diagnostics and connectivity checks

- `scripts/test_ccxt_bitget_live.py`
- `scripts/test_bitget_client.py`
- `scripts/diagnose_bitget.py`
- `scripts/debug_bitget_api.py`

Use these before blaming strategy logic when exchange/API behavior is unstable.

## 5) Recommended operating flow

1. Decide bot family first: Bitget spot, Futures, or MT5.
2. Start with dry-run mode and baseline metrics.
3. Run scanner and bot separately so signal quality and execution can be isolated.
4. Validate with backtest plus dry-run logs before any live switch.
5. Use one launcher surface: `scripts/bot_hub.ps1`.

## 6) Quick command checklist

- Show all targets: `./scripts/bot_hub.ps1`
- Run Bitget spot bot: `./scripts/bot_hub.ps1 -Target bitget-spot`
- Run futures bot: `./scripts/bot_hub.ps1 -Target futures`
- Run MT5 scanner: `./scripts/bot_hub.ps1 -Target mt5-scanner`
- Run MT5 scalper: `./scripts/bot_hub.ps1 -Target mt5-scalper`
- Run scanner dashboard: `./scripts/bot_hub.ps1 -Target dashboard`
- Check statuses: `./scripts/bot_hub.ps1 -Target status-spot` and `./scripts/bot_hub.ps1 -Target status-futures`

## 7) Notes to avoid confusion

- `src/main.py` and `scripts/run_bot.ps1` are legacy Binance-oriented.
- For active Bitget flow, prefer `src/main_bitget.py` and `scripts/run_bitget_bot.ps1`.
- Keep using `.venv/Scripts/python.exe` for reproducible behavior.
