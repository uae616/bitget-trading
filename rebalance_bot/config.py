"""
Configuration for the Bitget Rebalance Bot.

All settings can be overridden via environment variables or a .env file.
See .env.example for reference.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Bitget API credentials
# ---------------------------------------------------------------------------
API_KEY = os.getenv("BITGET_API_KEY", "")
API_SECRET = os.getenv("BITGET_API_SECRET", "")
API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE", "")

# Use the sandbox / simulated trading endpoint when True
USE_SANDBOX = os.getenv("BITGET_USE_SANDBOX", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Target portfolio allocations  (symbol -> fraction, must sum to 1.0)
# ---------------------------------------------------------------------------
# Example: 50 % BTC, 30 % ETH, 20 % USDT (as a stable-coin "cash" reserve)
TARGET_ALLOCATIONS: dict[str, float] = {
    "BTC": 0.50,
    "ETH": 0.30,
    "USDT": 0.20,
}

# ---------------------------------------------------------------------------
# Rebalancing parameters
# ---------------------------------------------------------------------------
# Only rebalance a coin when its actual weight deviates from the target by
# more than this fraction (e.g. 0.05 means 5 percentage points).
REBALANCE_THRESHOLD = float(os.getenv("REBALANCE_THRESHOLD", "0.05"))

# Quote currency used for valuation and as the settlement currency for orders.
QUOTE_CURRENCY = os.getenv("QUOTE_CURRENCY", "USDT")

# Minimum order size in quote currency (avoid dust orders).
MIN_ORDER_SIZE_QUOTE = float(os.getenv("MIN_ORDER_SIZE_QUOTE", "10.0"))

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
# How often to run the rebalance check (in minutes).
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
