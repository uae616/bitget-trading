import logging
from engine.execution_bitget import execute_actions_bitget

import sys
import os
# Add the parent directory (root) to the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from engine.execution_bitget import execute_actions_bitget
# ... rest of the script

# 1. Setup Mock Logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Test")

# 2. Mock State (Small Account: $52 Equity)
state = {
    "positions": {
        "SOL": {"amount": 0.25, "avg_cost": 85.0} # Value ~$22.40
    },
    "metrics": {},
    "meta": {"last_trade_ts": {}}
}

# 3. Mock Config (Your new gates)
cfg = {
    "bot": {"dry_run": True},
    "portfolio": {"quote_asset": "USDT", "max_trade_per_symbol_cooldown_sec": 0},
    "execution": {"min_sell_notional_usdt": 1.10}
}

# 4. Mock Filters (Bitget SOL precision)
spot_filters = {
    "SOL/USDT": {
        "min_notional": 1.0,
        "step_size": 0.01, # SOL typically has 2-3 decimals
        "min_qty": 0.001
    }
}

# 5. The Test Action (A $1.12 Harvest)
# Price is 89.63, Qty is 0.0125 -> Notional = 1.120375
test_actions = [{
    "coin": "SOL",
    "type": "TAKE_PROFIT_SELL",
    "qty": 0.0125, 
    "price": 89.63
}]

print("--- Starting Harvest Simulation ---")
results = execute_actions_bitget(cfg, state, test_actions, log, spot_filters=spot_filters)
print(f"--- Simulation Finished: {results[0]['status']} ---")
