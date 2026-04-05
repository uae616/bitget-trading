# Bitget Rebalance Bot

A lightweight Python bot that keeps your Bitget spot portfolio aligned with a
set of **target allocations** by automatically placing market orders whenever
the actual allocation drifts beyond a configurable threshold.

---

## Features

| Feature | Details |
|---|---|
| Target allocations | Configurable per-coin weights that sum to 100 % |
| Drift threshold | Only rebalances when a coin drifts more than *N* percentage points from its target (default 5 %) |
| Minimum order size | Skips dust orders below a configurable quote-currency value (default 10 USDT) |
| Dry-run mode | Logs planned orders without sending them to the exchange |
| Scheduler | Runs the rebalance check on a configurable interval (default every 60 minutes) |
| Testable design | Core logic is decoupled from the API client and covered by unit tests |

---

## Project structure

```
rebalance_bot/
├── .env.example        # Copy to .env and fill in your credentials
├── requirements.txt    # Python dependencies
├── config.py           # All settings (reads from environment / .env)
├── bitget_client.py    # Thin Bitget REST API wrapper
├── rebalance.py        # Core rebalancing logic (pure, testable)
├── main.py             # Entry-point with scheduler loop
└── tests/
    └── test_rebalance.py
```

---

## Quick start

### 1. Install dependencies

```bash
cd rebalance_bot
pip install -r requirements.txt
```

### 2. Configure credentials and allocations

```bash
cp .env.example .env
# Edit .env with your API key, secret, passphrase and desired allocations
```

The target allocations are set in `config.py` under `TARGET_ALLOCATIONS`.
Edit them to match your desired portfolio:

```python
TARGET_ALLOCATIONS = {
    "BTC":  0.50,   # 50 % Bitcoin
    "ETH":  0.30,   # 30 % Ethereum
    "USDT": 0.20,   # 20 % cash reserve
}
```

> **Important**: the values must sum to exactly `1.0`.

### 3. Run

**Dry-run (no orders placed)**

```bash
python main.py --dry-run
```

**Single check, live**

```bash
python main.py --once
```

**Continuous scheduler (default: every 60 minutes)**

```bash
python main.py
```

---

## Configuration reference

All settings can be overridden with environment variables or in `.env`:

| Variable | Default | Description |
|---|---|---|
| `BITGET_API_KEY` | – | Bitget API key |
| `BITGET_API_SECRET` | – | Bitget API secret |
| `BITGET_API_PASSPHRASE` | – | Bitget API passphrase |
| `BITGET_USE_SANDBOX` | `false` | Use simulated trading |
| `REBALANCE_THRESHOLD` | `0.05` | Min drift to trigger rebalance (5 %) |
| `QUOTE_CURRENCY` | `USDT` | Settlement / valuation currency |
| `MIN_ORDER_SIZE_QUOTE` | `10.0` | Min order in quote currency |
| `CHECK_INTERVAL_MINUTES` | `60` | Scheduler interval |
| `LOG_LEVEL` | `INFO` | Python logging level |

---

## Running tests

```bash
cd rebalance_bot
python -m pytest tests/ -v
```

All tests are offline (no exchange connection required).

---

## How it works

1. **Fetch balances** – retrieve all spot balances from Bitget.
2. **Fetch prices** – get the latest price for every held or targeted coin.
3. **Compute weights** – calculate each coin's current share of total portfolio value.
4. **Detect drift** – compare current weights against `TARGET_ALLOCATIONS`.
5. **Generate orders** – for each coin whose drift exceeds `REBALANCE_THRESHOLD`,
   create a market BUY or SELL order sized to bring it back to its target weight.
6. **Execute orders** – place the orders via the Bitget spot trading API
   (skipped in dry-run mode).

---

## Security notes

- Store credentials only in `.env` (never commit them).
- `.env` is listed in `.gitignore` by convention – double-check before pushing.
- Use a **read + trade only** API key (no withdrawal permission needed).
- Enable IP whitelisting on the API key for extra protection.
