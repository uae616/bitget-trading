import time
import traceback
import sys
from pathlib import Path


def _ensure_workspace_venv_python() -> bool:
    project_root = Path(__file__).resolve().parents[1]
    expected_windows = (project_root / ".venv" / "Scripts" / "python.exe").resolve()
    expected_unix = (project_root / ".venv" / "bin" / "python").resolve()
    expected_python = expected_windows if expected_windows.exists() else expected_unix

    if expected_python.exists():
        current_python = Path(sys.executable).resolve()
        if current_python != expected_python:
            print(
                "This bot instance must run with workspace venv Python: "
                f"{expected_python}. Current: {current_python}. Exiting."
            )
            return False
    return True


def minutes_to_bars(minutes: int, interval: str) -> int:
    """
    Convert minutes into candle-bars for a given interval.
    Supports '1m', '5m', '15m', '30m', '1h', '4h', etc.
    """
    interval = interval.strip().lower()
    if interval.endswith("m"):
        base = int(interval[:-1])
        return max(1, int(minutes / base))
    if interval.endswith("h"):
        base = int(interval[:-1]) * 60
        return max(1, int(minutes / base))
    # fallback: assume minutes
    return max(1, minutes)


def main():
    if not _ensure_workspace_venv_python():
        return

    from .core.settings import load_config
    from .core.logger import setup_logger
    from .core.persistence import load_state, save_state
    from .core.single_instance import acquire_single_instance_lock, AlreadyRunningError
    from .core.notify import send_telegram_message

    from .binance.rest_client import BinanceRestClient
    from .binance.spot_api import SpotAPI
    from .binance.convert_api import ConvertAPI

    from .data.spot_filters import build_spot_filters
    from .data.convert_limits import build_convert_limits

    from .engine.scanner import KlineScanner
    from .engine.strategy import decide_actions
    from .engine.execution import execute_actions
    from .engine.reconcile import maybe_reconcile
    from .engine.risk import evaluate_risk_guardrail

    try:
        instance_lock = acquire_single_instance_lock()
    except AlreadyRunningError:
        print("Another rebalance bot instance is already running. Exiting.")
        return

    cfg = load_config()
    log = setup_logger(cfg["bot"]["log_level"])
    log.info("Single-instance lock acquired.")
    state = load_state()

    risk_state = state.setdefault("risk", {})
    risk_state.setdefault("halted", False)
    risk_state.setdefault("halt_reason", "")
    risk_state.setdefault("current_day", "")
    risk_state.setdefault("day_start_equity_usdt", 0.0)
    risk_state.setdefault("last_alert_day", "")

    # ensure keys exist
    state.setdefault("pnl", {}).setdefault("fees_usdt", 0.0)
    state.setdefault("harvest", {}).setdefault("pending_profit_target", {})
    state.setdefault("meta", {}).setdefault("cycle", 0)
    state["meta"].setdefault("last_trade_ts", {})
    state["meta"].setdefault("locks", {})

    api_key = cfg["secrets"]["api_key"]
    api_secret = cfg["secrets"]["api_secret"]
    base_url = cfg["bot"]["base_url"]
    quote_asset = cfg["portfolio"]["quote_asset"]
    coins = cfg["portfolio"]["coins"]

    client = BinanceRestClient(api_key, api_secret, base_url=base_url, timeout=10)

    # time sync helps signed requests
    try:
        client.sync_time()
        log.info("Time sync OK.")
    except Exception as e:
        log.warning(f"Time sync failed: {e}")

    spot = SpotAPI(client, quote_asset=quote_asset)
    conv = ConvertAPI(client)

    # load spot filters once
    try:
        ex = spot.exchange_info()
        spot_filters = build_spot_filters(ex)
        log.info("Spot filters loaded.")
    except Exception as e:
        spot_filters = {}
        log.warning(f"Could not load spot filters: {e}")

    # convert limits (API-backed when available; safe defaults fallback)
    convert_limits = build_convert_limits(convert_api=conv, coins=coins, quote_asset=quote_asset)

    # --- Scanner configuration ---
    interval = "15m"
    limit = 120
    scanner = KlineScanner(spot_api=spot, quote_asset=quote_asset, interval=interval, limit=limit, ttl_sec=20)

    # horizons derived from config (minutes)
    h_short = int(cfg["momentum"]["short_min"])
    h_mid = int(cfg["momentum"]["mid_min"])
    h_long = int(cfg["momentum"]["long_min"])

    horizons = {
        "short": minutes_to_bars(h_short, interval),
        "mid": minutes_to_bars(h_mid, interval),
        "long": minutes_to_bars(h_long, interval),
    }

    weights = {
        "short": float(cfg["momentum"]["w_short"]),
        "mid": float(cfg["momentum"]["w_mid"]),
        "long": float(cfg["momentum"]["w_long"]),
    }

    # fee conversion uses last price from the snapshot if possible
    def fee_to_usdt(asset: str, amt: float):
        asset = asset.upper()
        if asset == quote_asset:
            return amt
        # try to fetch last price quickly via ticker (public)
        sym = f"{asset}{quote_asset}"
        try:
            px = float(spot.ticker_price(sym)["price"])
            return amt * px
        except Exception:
            return None

    cycle_s = int(cfg["bot"]["cycle_seconds"])
    dry_run = bool(cfg["bot"].get("dry_run", True))
    alerts_cfg = cfg.get("alerts", {})
    telegram_signals = bool(alerts_cfg.get("telegram_signals", False))
    telegram_near_miss = bool(alerts_cfg.get("telegram_near_miss", False))
    near_miss_cooldown_sec = int(alerts_cfg.get("near_miss_cooldown_sec", 600))

    alert_state = state.setdefault("meta", {}).setdefault("alerts", {})
    alert_state.setdefault("last_near_miss", {})
    log.info(f"✅ Bot started. DRY_RUN={dry_run} cycle={cycle_s}s interval={interval}")

    while True:
        t0 = time.time()
        state["meta"]["cycle"] = int(state["meta"].get("cycle", 0)) + 1
        max_cycles = int(cfg["bot"].get("max_cycles", 0)) 
        if max_cycles > 0 and state["meta"]["cycle"] >= max_cycles: 
            log.info(f"Experiment finished: reached max_cycles={max_cycles}")     
            save_state(state) 
            break
        state["meta"]["locks"] = {}
        log.info(f"Cycle {state['meta']['cycle']} running...")
        try:
            # 1) Scanner produces snapshot
            snapshot = scanner.full_scan(
                coins=coins,
                horizons=horizons,
                weights=weights,
                scanner_cfg=cfg.get("scanner", {}),
            )

            # 1.5) Risk guardrail check (halts trading actions if triggered)
            risk_status = evaluate_risk_guardrail(cfg, state, snapshot, log=log)
            if risk_status.get("triggered"):
                message = (
                    "🚨 Rebalance Bot HALTED\n"
                    f"Reason: {risk_status.get('reason', 'risk limit')}\n"
                    f"UTC Day: {risk_status.get('day')}"
                )
                send_telegram_message(cfg, message, log=log)

            if risk_status.get("halted"):
                log.warning(f"[RISK] Trading paused. {risk_status.get('reason', 'risk halt active')}")
                save_state(state)
                continue

            # 2) Strategy produces actions (no API calls)
            strategy_out = decide_actions(cfg, state, log, snapshot=snapshot, return_context=True)
            if isinstance(strategy_out, tuple) and len(strategy_out) == 2:
                actions, strategy_ctx = strategy_out
            else:
                actions = strategy_out
                strategy_ctx = {"signal": None, "near_miss": None}

            log.info(f"Actions count: {len(actions)}")
            if actions:
                log.info(f"Actions: {len(actions)}")

            signal = strategy_ctx.get("signal")
            if telegram_signals and signal:
                message = (
                    f"📈 Rebalance signal (cycle {state['meta']['cycle']})\n"
                    f"{signal}\n"
                    f"dry_run={dry_run}"
                )
                send_telegram_message(cfg, message, log=log)

            near_miss = strategy_ctx.get("near_miss")
            if telegram_near_miss and near_miss:
                import time as _time
                now_ts = int(_time.time())
                last_map = alert_state.setdefault("last_near_miss", {})
                last_ts = int(last_map.get(near_miss, 0))
                if now_ts - last_ts >= near_miss_cooldown_sec:
                    message = (
                        f"⚠️ Rebalance near-miss (cycle {state['meta']['cycle']})\n"
                        f"{near_miss}\n"
                        f"dry_run={dry_run}"
                    )
                    ok = send_telegram_message(cfg, message, log=log)
                    if ok:
                        last_map[near_miss] = now_ts

            # 3) Execution runs actions (Spot/Convert) and calls Accounting internally
            execute_actions(
                cfg, state, actions, log,
                spot_api=spot,
                convert_api=conv,
                spot_filters=spot_filters,
                convert_limits=convert_limits,
                fee_to_usdt_fn=fee_to_usdt,
                price_cache=None
            )

            # 4) Periodic reconciliation
            maybe_reconcile(cfg, state, log, spot_api=spot)

            # 5) Persist state
            save_state(state)

        except Exception as e:
            log.error(f"❌ Loop error: {e}")
            log.error(traceback.format_exc())
            time.sleep(5)

        elapsed = time.time() - t0
        time.sleep(max(1, cycle_s - elapsed))


if __name__ == "__main__":
    main()
