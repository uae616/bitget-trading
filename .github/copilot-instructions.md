# Project Guidelines

## Scope
- These instructions apply to the workspace root (`rebalance_bot`) unless a closer instruction file exists.
- For work inside `prompts.chat/`, follow `prompts.chat/AGENTS.md` as the primary local guidance.

## Code Style
- Preserve existing Python style and structure in `src/` modules; prefer small, focused changes.
- Keep public behavior stable unless explicitly requested.
- Use existing logging/state patterns from `src/core/logger.py` and `src/core/persistence.py`.
- Keep secrets in `.env` only; never hardcode credentials.

## Architecture
- Main Python app boundaries:
  - `src/core/`: config, logging, persistence, process lock, notifications
  - `src/data/`: price/filter/limit caches
  - `src/engine/`: scanning, strategy, execution, risk, reconcile/accounting
  - `src/bitget/`: Bitget/CCXT integration
  - `src/futures/`: futures bot logic
  - `src/main_bitget.py`, `src/main_futures.py`: current entry points
- Legacy Binance flow exists (`src/main.py`, `src/binance/`) and may still be referenced by old scripts/docs.

## Build and Test
- Environment setup (PowerShell): use `scripts/setup_venv.ps1`.
- Prefer workspace venv Python for all runs (`.venv/Scripts/python.exe` on Windows).
- Common run scripts:
  - `scripts/run_bitget_bot.ps1`
  - `scripts/run_futures_bot.ps1`
  - `scripts/status_bot.ps1`
  - `scripts/status_futures_bot.ps1`
- Python dependencies: `requirements.txt`.
- Root `package.json` is not the primary build/test authority for the Python bot.

## Conventions and Pitfalls
- `config.toml` + `.env` are both used by `src/core/settings.py`.
- Trading safety defaults are expected (`dry_run = true` unless explicitly changed).
- Single-instance lock behavior is intentional (`src/core/single_instance.py`).
- When updating docs, link existing files instead of duplicating large sections.

## Link-First References
- `README.md` (quick start and structure)
- `BITGET_INTEGRATION.md` (Bitget setup)
- `CCXT_MIGRATION.md` and `CCXT_MIGRATION_SUMMARY.md` (migration context)
- `DEPLOYMENT_CHECKLIST.md` and `DEPLOYMENT_READY.md` (deployment guidance)
- `STATUS.txt` (current migration/status snapshot)
- `prompts.chat/AGENTS.md` (instructions for the Next.js subproject)
