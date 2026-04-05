import sys
import src.main as m
from src.core import persistence as p

MAX = int(sys.argv[1])

orig_save = p.save_state

def save_and_stop(state):
    orig_save(state)
    if state.get("meta", {}).get("cycle", 0) >= MAX:
        raise SystemExit("Experiment finished")

p.save_state = save_and_stop

m.main()
