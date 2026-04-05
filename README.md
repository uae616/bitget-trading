# Rebalance Bot (Spot + Convert)

## Quick Start (Windows PowerShell)
1) Create venv + install deps:
\\\powershell
cd C:\Users\Administrator\rebalance_bot
.\scripts\setup_venv.ps1
copy .env.example .env
# edit .env with your keys
\\\

2) Run (DRY_RUN=true by default):
\\\powershell
.\scripts\run_bot.ps1
\\\

## Safety
- Default config uses DRY_RUN=true (no real trading).
- When you are ready, set \dry_run = false\ in config.toml.

## Structure
- src/binance: custom REST client + Spot/Convert wrappers
- src/data: caches (prices, filters, convert limits)
- src/engine: strategy + execution + accounting (WAC)
- src/main.py: continuous loop service

## Bots and Tools Map
- Central guide: `BOTS_AND_TOOLS_GUIDE.md`
- Unified launcher: `scripts/bot_hub.ps1`

## Futures Smart Portfolio Bot (New)
- Entry point: `python -m src.main_futures`
- Run script: `./scripts/run_futures_bot.ps1`
- Status script: `./scripts/status_futures_bot.ps1`
- Log file: `logs/futures_bot.log`
- State file: `state/futures_state.json`

### Safety Defaults
- Futures mode starts in `dry_run = true` under `[futures_bot]`.
- Max leverage is capped in code to `<= 5x` even if config is higher.
- Built-in guards:
	- max total exposure
	- max per-asset exposure
	- stop-loss / take-profit exits
	- drawdown auto-pause
	- optional risk auto-close (flatten) on drawdown pause
	- optional auto-close on futures signal flip

### Config Sections
- `[futures_bot]` basic runtime settings, symbols, cycle interval
- `[futures_strategy]` RSI + MA directional signal thresholds
- `[futures_risk]` exposure, SL/TP, drawdown pause limits
- `[futures_funding]` funding-rate hedge trigger and allocation

### Dashboard Notes
- Unified scanner dashboard now separates **Spot Positions** and **Futures Positions**.
- It also shows **Auto-Trade Activity** (signal/risk events and futures bot activities).
- It now includes **Performance metrics** (closed trades, win rate, net/avg realized PnL % from auto-close activities).
- It also shows **spot auto-trade counters** (spot buys, spot sells, spot realized PnL from `state/state.json`).
