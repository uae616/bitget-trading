from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

STATE_PATH = Path("state") / "mt5_scalper_state.json"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_state() -> dict:
    STATE_PATH.parent.mkdir(exist_ok=True)
    if not STATE_PATH.exists():
        return {
            "meta": {"cycle": 0, "last_run": ""},
            "positions": {},
            "activities": [],
        }
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "meta": {"cycle": 0, "last_run": ""},
            "positions": {},
            "activities": [],
        }


def save_state(state: dict) -> None:
    state.setdefault("meta", {})["last_run"] = _utc_iso()
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def add_activity(state: dict, action: str, symbol: str, message: str, price: float = 0.0) -> None:
    acts = state.setdefault("activities", [])
    acts.append({"ts": _utc_iso(), "action": action, "symbol": symbol, "message": message, "price": price})
    if len(acts) > 500:
        del acts[:-500]
