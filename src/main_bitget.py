import sys
import time
import traceback
from pathlib import Path

# Ensure `core`, `engine`, and `utils` resolve when running `python -m src.main_bitget`.
_SRC_ROOT = Path(__file__).resolve().parent
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


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
    """Convert minutes into candle-bars for a given interval."""
    interval = interval.strip().lower()
    if interval.endswith("m"):
        base = int(interval[:-1])
        return max(1, int(minutes / base))
    if interval.endswith("h"):
        base = int(interval[:-1]) * 60
        return max(1, int(minutes / base))
    return max(1, minutes)


def main():
    if not _ensure_workspace_venv_python():
        return

    from core.settings import load_config
    from core.logger import setup_logger
    from core.persistence import load_state, save_state
    from core.single_instance import acquire_single_instance_lock, AlreadyRunningError
    from core.notify import send_telegram_message

    import ccxt
    
    from engine.scanner import KlineScanner
    from engine.strategy import decide_actions
    from engine.execution_bitget import execute_actions_bitget
    from engine.reconcile import maybe_reconcile
    from engine.risk import evaluate_risk_guardrail

    try:
        instance_lock = acquire_single_instance_lock()
    except AlreadyRunningError:
        print("Another rebalance bot instance is already running. Exiting.")
        return

    cfg = load_config()
    log = setup_logger(cfg.get("bot", {}).get("log_level", "INFO"))
    log.info("Single-instance lock acquired.")
    log.info("Using Bitget exchange (CCXT)")
    state = load_state()

    # Initialize state structures
    risk_state = state.setdefault("risk", {})
    risk_state.setdefault("halted", False)
    risk_state.setdefault("halt_reason", "")
    risk_state.setdefault("current_day", "")
    risk_state.setdefault("day_start_equity_usdt", 0.0)
    risk_state.setdefault("last_alert_day", "")

    state.setdefault("pnl", {}).setdefault("fees_usdt", 0.0)
    state.setdefault("harvest", {}).setdefault("pending_profit_target", {})
    state.setdefault("meta", {}).setdefault("cycle", 0)
    state["meta"].setdefault("last_trade_ts", {})
    state["meta"].setdefault("locks", {})

    # Load Bitget credentials
    api_key = cfg["secrets"]["bitget_api_key"]
    api_secret = cfg["secrets"]["bitget_api_secret"]
    api_passphrase = cfg["secrets"]["bitget_api_passphrase"]
    quote_asset = cfg["portfolio"]["quote_asset"]
    coins = cfg["portfolio"]["coins"]

    # Initialize CCXT Bitget exchange
    try:
        exchange = ccxt.bitget({
            'apiKey': api_key,
            'secret': api_secret,
            'password': api_passphrase,  # Passphrase for Bitget
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',  # Use spot trading by default
                'createMarketBuyOrderRequiresPrice': False,
            }
        })
        log.info("✅ Bitget exchange initialized via CCXT")
    except Exception as e:
        log.error(f"❌ Failed to initialize Bitget: {e}")
        return

    # Build symbol names in CCXT format (BTC/USDT)
    ccxt_symbols = [f"{coin}/{quote_asset}" for coin in coins]
    log.info(f"Monitoring symbols: {ccxt_symbols}")

    # Helper to fetch filters/limits from exchange
    try:
        exchange.load_markets()
        log.info("✅ Markets loaded")
    except Exception as e:
        log.warning(f"Could not load markets: {e}")

    # Create spot_filters dict compatible with execution layer
    spot_filters = {}
    for symbol_ccxt in ccxt_symbols:
        if symbol_ccxt in exchange.symbols:
            market = exchange.market(symbol_ccxt)
            # Extract limits (CCXT format)
            limits = market.get('limits', {})
            amount_limits = limits.get('amount', {})
            cost_limits = limits.get('cost', {})
            
            # Map to our filter format
            spot_filters[symbol_ccxt] = {
                'min_notional': cost_limits.get('min', 0),
                'step_size': market.get('precision', {}).get('amount', 0.00001),
                'min_qty': amount_limits.get('min', 0),
            }
        else:
            log.warning(f"Symbol {symbol_ccxt} not found on Bitget")

    # Scanner configuration
    interval = "15m"
    limit = 120
    
    # Create a wrapper spot_api-like object for CCXT
    class CCXTSpotWrapper:
        def __init__(self, exchange_instance):
            self.exchange = exchange_instance
        
        def account(self):
            """Fetch account balances"""
            balance = self.exchange.fetch_balance()
            return balance
        
        def ticker_price(self, symbol):
            """Fetch current ticker"""
            ticker = self.exchange.fetch_ticker(symbol)
            return {'data': {'lastPr': str(ticker['last'])}}
        
        def klines(self, symbol, interval='15m', limit=120):
            """Fetch OHLCV candles
            
            Note: Scanner expects CCXTUSDT format but we need to convert to BTC/USDT for CCXT.
            Also, scanner expects the list directly, not wrapped in {'data': ...}.
            """
            # symbol comes in as BTCUSDT from scanner, convert to BTC/USDT for CCXT
            if '/' not in symbol:
                # Insert / before last part (quote asset) - assumes 3 or 4 char quote (e.g., USDT, BUSD, etc.)
                for quote in ['USDT', 'BUSD', 'USDC', 'DAI', 'TUSD']:
                    if symbol.endswith(quote):
                        symbol = symbol[:-len(quote)] + '/' + quote
                        break
            
            timeframe = interval  # CCXT uses same format
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            # Return the list directly (not wrapped in {'data': ...})
            return ohlcv
    
    spot = CCXTSpotWrapper(exchange)

    scanner = KlineScanner(spot_api=spot, quote_asset=quote_asset, interval=interval, limit=limit, ttl_sec=20)

    # Momentum horizons
    h_short = int(cfg.get("momentum", {}).get("short_min", 30))
    h_mid = int(cfg.get("momentum", {}).get("mid_min", 240))
    h_long = int(cfg.get("momentum", {}).get("long_min", 1440))

    horizons = {
        "short": minutes_to_bars(h_short, interval),
        "mid": minutes_to_bars(h_mid, interval),
        "long": minutes_to_bars(h_long, interval),
    }

    weights = {
        "short": float(cfg.get("momentum", {}).get("w_short", 0.5)),
        "mid": float(cfg.get("momentum", {}).get("w_mid", 0.3)),
        "long": float(cfg.get("momentum", {}).get("w_long", 0.2)),
    }

    # Helper to convert fees to USDT
    def fee_to_usdt(asset: str, amt: float):
        asset = asset.upper()
        if asset == quote_asset:
            return amt
        sym = f"{asset}/{quote_asset}"
        try:
            ticker = exchange.fetch_ticker(sym)
            px = ticker['last']
            return amt * px
        except Exception:
            return 0.0

    # Telegram notifications
    telegram_enabled = cfg["secrets"].get("telegram_enabled", False)
    telegram_token = cfg["secrets"].get("telegram_token", "")
    telegram_chat_id = cfg["secrets"].get("telegram_chat_id", "")

    # Main bot loop
    log.info("Bot starting. Press Ctrl+C to stop.")
    cycle = 0
    max_cycles = int(cfg.get("bot", {}).get("max_cycles", 0))

    try:
        while True:
            cycle += 1
            state["meta"]["cycle"] = cycle

            if max_cycles > 0 and cycle > max_cycles:
                log.info(f"Reached max cycles ({max_cycles}). Stopping.")
                break

            try:
                # Fetch current account state
                try:
                    balance = exchange.fetch_balance()
                except Exception as e:
                    log.warning(f"Account fetch failed: {e}")
                    balance = {}

                # Update positions from account
                positions = state.setdefault("positions", {})
                for coin in coins:
                    if coin not in balance:
                        log.debug(f"{coin} not in account response")
                        continue

                    coin_balance = balance[coin]
                    amount = coin_balance.get('free', 0.0)

                    if coin not in positions:
                        positions[coin] = {
                            "amount": amount,
                            "avg_cost": 0.0,
                            "pnl_realized": 0.0,
                            "fees": 0.0,
                            "pnl_unrealized": 0.0,
                            "cost_basis": 0.0,
                        }
                    else:
                        positions[coin]["amount"] = amount

                # Update USDT cash
                if quote_asset in balance:
                    state["cash_usdt"] = balance[quote_asset].get('free', 0.0)

                # Strategy decisions
                snapshot = scanner.full_scan(
                    coins=coins,
                    horizons=horizons,
                    weights=weights,
                    scanner_cfg=cfg.get("scanner", {}),
                )
                actions = decide_actions(cfg, state, log, snapshot=snapshot)

                # Execute trades
                execute_actions_bitget(
                    cfg=cfg,
                    state=state,
                    actions=actions,
                    log=log,
                    spot_api=spot,
                    spot_filters=spot_filters,
                    fee_to_usdt_fn=fee_to_usdt,
                    price_cache=None,
                )

                # Reconciliation
                maybe_reconcile(cfg=cfg, state=state, log=log, spot_api=spot)

                # Risk evaluation
                risk_result = evaluate_risk_guardrail(cfg=cfg, state=state, snapshot=snapshot, log=log)
                if risk_result.get("triggered") and telegram_enabled:
                    msg = f"⚠️ Risk guardrail triggered: {risk_result.get('reason', 'Unknown')}"
                    send_telegram_message(telegram_token, telegram_chat_id, msg)

                # Save state
                save_state(state)
                
                # Cycle delay
                cycle_seconds = int(cfg.get("bot", {}).get("cycle_seconds", 1))
                time.sleep(cycle_seconds)

            except Exception as e:
                log.error(f"Cycle error: {e}\n{traceback.format_exc()}")
                time.sleep(5)

    except KeyboardInterrupt:
        log.info("Keyboard interrupt. Saving state and exiting.")
        save_state(state)


if __name__ == "__main__":
    main()
