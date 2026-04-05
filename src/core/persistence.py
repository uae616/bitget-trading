import json
from pathlib import Path

STATE_PATH = Path("state/state.json")

def load_state() -> dict:
    STATE_PATH.parent.mkdir(exist_ok=True)
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    raise FileNotFoundError("state/state.json not found. Run bootstrap again.")

def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
