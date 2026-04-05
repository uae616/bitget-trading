import json
from pathlib import Path

STATE_PATH = Path("state/futures_state.json")


def load_futures_state() -> dict:
    STATE_PATH.parent.mkdir(exist_ok=True)
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {
        "meta": {
            "cycle": 0,
            "paused": False,
            "pause_reason": "",
            "risk_flattened": False,
        },
        "risk": {
            "equity_peak_usdt": 0.0,
            "last_equity_usdt": 0.0,
        },
        "hedges": {},
        "position_protection": {},
        "activities": [],
    }


def save_futures_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
