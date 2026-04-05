import json
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "state" / "state.json"


def _price_usdt(symbol: str) -> float | None:
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return float(payload["price"])
    except Exception:
        return None


def _load_state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def _flatten_numeric_metrics(metrics: dict | None) -> dict[str, float]:
    flat: dict[str, float] = {}

    def _walk(prefix: str, value):
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            flat[prefix] = float(value)
            return
        if isinstance(value, dict):
            for k, v in value.items():
                key = str(k)
                next_prefix = f"{prefix}.{key}" if prefix else key
                _walk(next_prefix, v)

    _walk("", metrics or {})
    return flat


def make_snapshot() -> dict:
    state = _load_state()
    positions = state.get("positions", {}) or {}

    prices = {}
    equity = float(state.get("cash_usdt", 0.0))
    for coin, pos in positions.items():
        amount = float(pos.get("amount", 0.0))
        market_px = _price_usdt(coin.upper())
        if market_px is None:
            market_px = float(pos.get("avg_price", 0.0))
        prices[coin.upper()] = market_px
        equity += amount * market_px

    return {
        "cycle": int(state.get("meta", {}).get("cycle", 0)),
        "equity_usdt": float(equity),
        "cash_usdt": float(state.get("cash_usdt", 0.0)),
        "realized_profit_usdt": float(state.get("pnl", {}).get("realized_profit_usdt", 0.0)),
        "harvested_profit_usdt": float(state.get("pnl", {}).get("harvested_profit_usdt", 0.0)),
        "fees_usdt": float(state.get("pnl", {}).get("fees_usdt", 0.0)),
        "prices": prices,
        "metrics": state.get("metrics", {}) or {},
    }


def compare(before_path: Path, after_path: Path) -> dict:
    before = json.loads(before_path.read_text(encoding="utf-8"))
    after = json.loads(after_path.read_text(encoding="utf-8"))

    before_equity = float(before["equity_usdt"])
    after_equity = float(after["equity_usdt"])
    equity_delta = after_equity - before_equity
    roi_pct = (equity_delta / before_equity * 100.0) if before_equity != 0 else 0.0
    fees_delta = float(after["fees_usdt"]) - float(before["fees_usdt"])
    net_after_fees = equity_delta - fees_delta

    before_metrics = _flatten_numeric_metrics(before.get("metrics", {}))
    after_metrics = _flatten_numeric_metrics(after.get("metrics", {}))
    metric_keys = set(before_metrics.keys()) | set(after_metrics.keys())
    metrics_delta = {
        k: float(after_metrics.get(k, 0.0) - before_metrics.get(k, 0.0))
        for k in sorted(metric_keys)
        if float(after_metrics.get(k, 0.0) - before_metrics.get(k, 0.0)) != 0.0
    }

    blocking = [
        (k, v)
        for k, v in metrics_delta.items()
        if k.startswith("strategy.no_buy.") and v > 0
    ]
    blocking.sort(key=lambda item: item[1], reverse=True)
    top_blocking = [
        {"reason": k.removeprefix("strategy.no_buy."), "count": float(v)}
        for k, v in blocking[:3]
    ]
    if top_blocking:
        summary_line = "Top blocks: " + ", ".join(
            f"{item['reason']}={item['count']:.0f}" for item in top_blocking
        )
    else:
        summary_line = "Top blocks: none"

    outcomes = [
        (k, v)
        for k, v in metrics_delta.items()
        if k.startswith("execution.status.") and v > 0
    ]
    outcomes.sort(key=lambda item: item[1], reverse=True)
    top_outcomes = [
        {"status": k.removeprefix("execution.status."), "count": float(v)}
        for k, v in outcomes[:3]
    ]
    if top_outcomes:
        outcomes_line = "Top outcomes: " + ", ".join(
            f"{item['status']}={item['count']:.0f}" for item in top_outcomes
        )
    else:
        outcomes_line = "Top outcomes: none"

    return {
        "before": before,
        "after": after,
        "delta": {
            "cycles": int(after["cycle"]) - int(before["cycle"]),
            "equity_usdt": equity_delta,
            "roi_pct": roi_pct,
            "cash_usdt": float(after["cash_usdt"]) - float(before["cash_usdt"]),
            "realized_profit_usdt": float(after["realized_profit_usdt"]) - float(before["realized_profit_usdt"]),
            "harvested_profit_usdt": float(after["harvested_profit_usdt"]) - float(before["harvested_profit_usdt"]),
            "fees_usdt": fees_delta,
            "net_after_fees_usdt": net_after_fees,
            "metrics": metrics_delta,
        },
        "summary": {
            "top_blocking_reasons": top_blocking,
            "top_execution_outcomes": top_outcomes,
            "line": summary_line,
            "outcomes_line": outcomes_line,
        },
    }


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage:")
        print("  checkpoint_metrics.py snapshot <output_json>")
        print("  checkpoint_metrics.py compare <before_json> <after_json> <output_json>")
        return 1

    mode = sys.argv[1].strip().lower()
    if mode == "snapshot":
        out_path = Path(sys.argv[2])
        snap = make_snapshot()
        out_path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
        print(json.dumps(snap, indent=2))
        return 0

    if mode == "compare":
        if len(sys.argv) < 5:
            print("compare mode needs: <before_json> <after_json> <output_json>")
            return 1
        before_path = Path(sys.argv[2])
        after_path = Path(sys.argv[3])
        out_path = Path(sys.argv[4])
        report = compare(before_path, after_path)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0

    print(f"Unknown mode: {mode}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
