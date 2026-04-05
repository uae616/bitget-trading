import time
import traceback

from .core.settings import load_config
from .core.logger import setup_logger
from .core.persistence import load_state, save_state

from .binance.rest_client import BinanceRestClient
from .binance.spot_api import SpotAPI
from .binance.convert_api import ConvertAPI

from .data.price_cache import PriceCache
from .data.spot_filters import build_spot_filters
from .data.convert_limits import build_convert_limits

from .engine.strategy import decide_actions
from .engine.execution import execute_actions
from .engine.reconcile import maybe_reconcile

def main():
    cfg = load_config()
    log = setup_logger(cfg['bot']['log_level'])

    state = load_state()
    state.setdefault('pnl', {}).setdefault('fees_usdt', 0.0)
    state.setdefault('harvest', {}).setdefault('pending_profit_target', {})
    state.setdefault('meta', {}).setdefault('cycle', 0)
    state['meta'].setdefault('last_trade_ts', {})
    state['meta'].setdefault('locks', {})

    api_key = cfg['secrets']['api_key']
    api_secret = cfg['secrets']['api_secret']
    base_url = cfg['bot']['base_url']

    client = BinanceRestClient(api_key, api_secret, base_url=base_url, timeout=10)

    # Time sync helps signed requests
    try:
        client.sync_time()
        log.info('Time sync OK.')
    except Exception as e:
        log.warning(f'Time sync failed: {e}')

    spot = SpotAPI(client, quote_asset=cfg['portfolio']['quote_asset'])
    conv = ConvertAPI(client)

    price_cache = PriceCache(spot, ttl_sec=3.0)

    # Build Spot filters cache once at startup (public endpoint)
    try:
        ex = spot.exchange_info()
        spot_filters = build_spot_filters(ex)
        log.info('Spot filters loaded.')
    except Exception as e:
        spot_filters = {}
        log.warning(f'Could not load spot filters: {e}')

    # Convert limits defaults (safe). Replace later with real Convert fetch if you want.
    convert_limits = build_convert_limits()

    # fee conversion uses last ticker price
    def fee_to_usdt(asset: str, amt: float):
        asset = asset.upper()
        if asset == cfg['portfolio']['quote_asset']:
            return amt
        sym = f\"{asset}{cfg['portfolio']['quote_asset']}\"
        try:
            px = price_cache.get_last_price(sym)
            return amt * px
        except Exception:
            return None

    cycle_s = int(cfg['bot']['cycle_seconds'])
    log.info(f\"✅ Bot started. DRY_RUN={cfg['bot'].get('dry_run', True)} cycle={cycle_s}s\")

    while True:
        t0 = time.time()
        state['meta']['cycle'] = int(state['meta'].get('cycle', 0)) + 1
        state['meta']['locks'] = {}

        try:
            actions = decide_actions(cfg, state, log, price_cache=price_cache)
            if actions:
                log.info(f\"Actions: {len(actions)}\")
            execute_actions(cfg, state, actions, log,
                           spot_api=spot,
                           convert_api=conv,
                           spot_filters=spot_filters,
                           convert_limits=convert_limits,
                           fee_to_usdt_fn=fee_to_usdt,
                           price_cache=price_cache)

            maybe_reconcile(cfg, state, log, spot_api=spot)
            save_state(state)

        except Exception as e:
            log.error(f\"❌ Loop error: {e}\")
            log.error(traceback.format_exc())
            time.sleep(5)

        elapsed = time.time() - t0
        time.sleep(max(1, cycle_s - elapsed))

if __name__ == '__main__':
    main()
