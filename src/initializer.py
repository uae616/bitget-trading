"""
initializer.py
-----------------------------------------
Option A Bootstrap:
- Uses ONLY coins listed in config.toml [portfolio].coins
- Reads current Spot balances for those coins + USDT
- Fetches current market price (COINUSDT)
- Sets baseline avg_price = current price
- Sets pending profit targets to 0
- Resets PnL counters (realized/fees) to 0

This treats your current holdings as if "bought today".
"""

import json
from pathlib import Path

from src.core.settings import load_config
from src.core.logger import setup_logger
from src.binance.rest_client import BinanceRestClient
from src.binance.spot_api import SpotAPI
from src.utils.symbols import spot_symbol

STATE_PATH = Path("state/state.json")


def fetch_free_balances(spot: SpotAPI) -> dict:
    """Return {asset: free_amount} for assets with free > 0."""
    acct = spot.account()
    out = {}
    for b in acct.get("balances", []):
        free_amt = float(b.get("free", 0.0))
        if free_amt > 0:
            out[b["asset"].upper()] = free_amt
    return out


def safe_last_price(spot: SpotAPI, coin: str, quote: str, log) -> float | None:
    """Return last price for COINQUOTE (e.g., BTCUSDT), or None if not available."""
    sym = spot_symbol(coin, quote)
    try:
        data = spot.ticker_price(sym)
        return float(data["price"])
    except Exception as e:
        log.warning(f"Price fetch failed for {sym}: {e}")
        return None


def build_state(cfg: dict, spot: SpotAPI, log) -> dict:
    coins = [c.upper() for c in cfg["portfolio"]["coins"]]
    quote = cfg["portfolio"]["quote_asset"].upper()

    log.info("Fetching spot balances...")
    balances = fetch_free_balances(spot)

    cash_usdt = float(balances.get(quote, 0.0))
    positions = {}
    pending_profit_target = {}

    log.info(f"Initializing ONLY config coins: {coins}")
    for coin in coins:
        amt = float(balances.get(coin, 0.0))
        if amt <= 0:
            log.info(f"Coin {coin}: balance=0 (skipped)")
            continue

        px = safe_last_price(spot, coin, quote, log)
        if px is None:
            log.warning(f"Coin {coin}: no {coin}{quote} price (skipped)")
            continue

        positions[coin] = {
            "amount": amt,
            "avg_price": px
        }
        pending_profit_target[coin] = 0.0

        log.info(f"Init {coin}: amount={amt} avg_price(baseline)={px}")

    state = {
        "cash_usdt": cash_usdt,
        "positions": positions,
        "pnl": {
            "realized_profit_usdt": 0.0,
            "harvested_profit_usdt": 0.0,
            "fees_usdt": 0.0
        },
        "harvest": {
            "pending_profit_target": pending_profit_target
        },
        "meta": {
            "cycle": 0,
            "last_trade_ts": {},
            "locks": {}
        }
    }

    log.info(f"USDT cash initialized: {cash_usdt}")
    return state


def save_state(state: dict, log):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    log.info(f"State saved to: {STATE_PATH.resolve()}")


def main():
    cfg = load_config()
    log = setup_logger(cfg["bot"]["log_level"])

    api_key = cfg["secrets"]["api_key"]
    api_secret = cfg["secrets"]["api_secret"]
    if not api_key or not api_secret:
        raise RuntimeError("Missing BINANCE_API_KEY or BINANCE_API_SECRET in .env")

    client = BinanceRestClient(api_key, api_secret, base_url=cfg["bot"]["base_url"], timeout=10)
    client.sync_time()

    spot = SpotAPI(client, quote_asset=cfg["portfolio"]["quote_asset"])

    log.info("=== INITIALIZER START ===")
    state = build_state(cfg, spot, log)
    save_state(state, log)
    log.info("=== INITIALIZER COMPLETE ===")


if __name__ == "__main__":
    main()
