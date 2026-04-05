# ==============================================
# bootstrap.ps1
# One-run scaffold that writes starter CONTENT
# into all key files for the rebalance bot.
# Project root: current directory.
# ==============================================

$ErrorActionPreference = "Stop"
$proj = (Get-Location).Path

function Write-File([string]$relPath, [string]$content) {
  $path = Join-Path $proj $relPath
  $dir = Split-Path -Parent $path
  if ($dir -and !(Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
  Set-Content -Path $path -Value $content -Encoding UTF8
}

function Touch([string]$relPath) {
  $path = Join-Path $proj $relPath
  $dir = Split-Path -Parent $path
  if ($dir -and !(Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
  if (!(Test-Path $path)) { New-Item -ItemType File -Path $path | Out-Null }
}

# ------------------------------------------------
# Root files
# ------------------------------------------------
Write-File ".gitignore" @"
.venv/
__pycache__/
*.pyc
*.log
state/state.json
state/cache.json
.env
"@

Write-File ".env.example" @"
BINANCE_API_KEY=""""
BINANCE_API_SECRET=""""
TELEGRAM_TOKEN=""""
TELEGRAM_CHAT_ID=""""
"@

Write-File "requirements.txt" @"
requests==2.32.3
python-dotenv==1.0.1
tomli==2.0.1; python_version < "3.11"
"@

Write-File "README.md" @"
# Rebalance Bot (Spot + Convert)

## Quick Start (Windows PowerShell)
1) Create venv + install deps:
\`\`\`powershell
cd C:\Users\Administrator\rebalance_bot
.\scripts\setup_venv.ps1
copy .env.example .env
# edit .env with your keys
\`\`\`

2) Run (DRY_RUN=true by default):
\`\`\`powershell
.\scripts\run_bot.ps1
\`\`\`

## Safety
- Default config uses DRY_RUN=true (no real trading).
- When you are ready, set \`dry_run = false\` in config.toml.

## Structure
- src/binance: custom REST client + Spot/Convert wrappers
- src/data: caches (prices, filters, convert limits)
- src/engine: strategy + execution + accounting (WAC)
- src/main.py: continuous loop service
"@

Write-File "config.toml" @"
[bot]
cycle_seconds = 30
reconcile_every_cycles = 60
log_level = "INFO"
base_url = "https://api.binance.com"
dry_run = true

[portfolio]
# coin symbols (base assets). Spot symbols are auto-mapped to COINUSDT.
coins = ["BTC","ETH","SOL"]
quote_asset = "USDT"
max_trade_per_symbol_cooldown_sec = 300

[profit_take]
enabled = true
profit_harvest_ratio = 0.20
min_profit_target_usdt = 1.0
max_sell_value_ratio_per_cycle = 0.02

[dip_buy]
enabled = true
min_buy_usdt = 5.0
max_buy_value_ratio_per_cycle = 0.02
require_momentum_not_too_negative = true
momentum_floor_z = -0.5

[momentum]
short_min = 30
mid_min = 240
long_min = 1440
w_short = 0.5
w_mid = 0.3
w_long = 0.2
"@

# ------------------------------------------------
# Scripts
# ------------------------------------------------
Write-File "scripts\setup_venv.ps1" @"
cd C:\Users\Administrator\rebalance_bot
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
Write-Host "✅ venv ready" -ForegroundColor Green
"@

Write-File "scripts\run_bot.ps1" @"
cd C:\Users\Administrator\rebalance_bot
.\.venv\Scripts\python.exe -m src.main
"@

# ------------------------------------------------
# State defaults
# ------------------------------------------------
Write-File "state\state.json" @"
{
  "cash_usdt": 0.0,
  "positions": {},
  "pnl": {
    "realized_profit_usdt": 0.0,
    "harvested_profit_usdt": 0.0,
    "fees_usdt": 0.0
  },
  "harvest": {
    "pending_profit_target": {}
  },
  "meta": {
    "cycle": 0,
    "last_trade_ts": {},
    "locks": {}
  }
}
"@

# ------------------------------------------------
# Python package init files (IMPORTANT for -m src.main)
# ------------------------------------------------
Touch "src\__init__.py"
Touch "src\core\__init__.py"
Touch "src\binance\__init__.py"
Touch "src\data\__init__.py"
Touch "src\engine\__init__.py"
Touch "src\utils\__init__.py"

# ------------------------------------------------
# src/core
# ------------------------------------------------
Write-File "src\core\logger.py" @"
import logging
from pathlib import Path

def setup_logger(level: str = "INFO", log_file: str = "logs/bot.log"):
    Path("logs").mkdir(exist_ok=True)
    logger = logging.getLogger("rebalance_bot")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")

    if not logger.handlers:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)

        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    logger.propagate = False
    return logger
"@

Write-File "src\core\errors.py" @"
class BotError(Exception):
    pass

class BinanceAPIError(BotError):
    def __init__(self, status_code: int, payload: str):
        super().__init__(f"Binance API error {status_code}: {payload}")
        self.status_code = status_code
        self.payload = payload
"@

Write-File "src\core\persistence.py" @"
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
"@

Write-File "src\core\settings.py" @"
import os
from dotenv import load_dotenv

def load_config() -> dict:
    load_dotenv()
    try:
        import tomllib  # py>=3.11
    except Exception:
        import tomli as tomllib

    with open('config.toml', 'rb') as f:
        cfg = tomllib.load(f)

    cfg['secrets'] = {
        'api_key': os.getenv('BINANCE_API_KEY', ''),
        'api_secret': os.getenv('BINANCE_API_SECRET', ''),
        'telegram_token': os.getenv('TELEGRAM_TOKEN', ''),
        'telegram_chat_id': os.getenv('TELEGRAM_CHAT_ID', ''),
    }
    return cfg
"@

Write-File "src\core\clock.py" @"
import time

class TimeSync:
    def __init__(self):
        self.offset_ms = 0

    def set_offset(self, server_time_ms: int):
        local_ms = int(time.time() * 1000)
        self.offset_ms = server_time_ms - local_ms

    def now_ms(self) -> int:
        return int(time.time() * 1000) + int(self.offset_ms)
"@

# ------------------------------------------------
# src/utils
# ------------------------------------------------
Write-File "src\utils\math_utils.py" @"
from decimal import Decimal, ROUND_DOWN

def floor_to_step(qty: float, step: float) -> float:
    q = Decimal(str(qty))
    s = Decimal(str(step))
    if s == 0:
        return float(q)
    return float((q // s) * s)

def floor_to_precision(qty: float, precision: int) -> float:
    q = Decimal(str(qty))
    quant = Decimal('1').scaleb(-precision)  # 10^-precision
    return float(q.quantize(quant, rounding=ROUND_DOWN))
"@

Write-File "src\utils\symbols.py" @"
def spot_symbol(coin: str, quote: str = 'USDT') -> str:
    return f\"{coin.upper()}{quote.upper()}\"

def pair_key(from_asset: str, to_asset: str) -> str:
    return f\"{from_asset.upper()}->{to_asset.upper()}\"
"@

# ------------------------------------------------
# src/binance - REST client (custom signed requests)
# ------------------------------------------------
Write-File "src\binance\rest_client.py" @"
import time
import hmac
import hashlib
import urllib.parse
import requests

from ..core.errors import BinanceAPIError
from ..core.clock import TimeSync

class BinanceRestClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str = 'https://api.binance.com', timeout: int = 10):
        self.api_key = api_key or ''
        self.api_secret = api_secret or ''
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        self.clock = TimeSync()

    # ---------- low-level helpers ----------
    def _build_query(self, params: dict) -> str:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        normalized = {}
        for k, v in params.items():
            normalized[k] = str(v)
        return urllib.parse.urlencode(normalized, doseq=True, safe='~')

    def _sign(self, query: str) -> str:
        return hmac.new(self.api_secret.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()

    def _request(self, method: str, path: str, params=None, signed=False, retries: int = 2):
        url = f\"{self.base_url}{path}\"
        headers = {}
        if self.api_key:
            headers['X-MBX-APIKEY'] = self.api_key

        if params is None:
            params = {}

        if signed:
            params.setdefault('timestamp', self.clock.now_ms() if self.clock else int(time.time() * 1000))
            params.setdefault('recvWindow', 5000)

            query = self._build_query(params)
            sig = self._sign(query)
            full_query = f\"{query}&signature={sig}\" if query else f\"signature={sig}\"
            url = f\"{url}?{full_query}\"
            data = None
        else:
            # public GETs can use params
            data = None

        last_exc = None
        for _ in range(retries + 1):
            try:
                r = self.session.request(method.upper(), url, params=None if signed else params, headers=headers, data=data, timeout=self.timeout)
                if r.status_code >= 400:
                    raise BinanceAPIError(r.status_code, r.text)
                return r.json()
            except Exception as e:
                last_exc = e
                time.sleep(0.5)

        raise last_exc

    # ---------- public endpoints ----------
    def ping(self):
        return self._request('GET', '/api/v3/ping', signed=False)

    def server_time(self):
        return self._request('GET', '/api/v3/time', signed=False)

    def sync_time(self):
        st = self.server_time()
        if 'serverTime' in st:
            self.clock.set_offset(int(st['serverTime']))
        return st

    def public_get(self, path: str, params=None):
        return self._request('GET', path, params=params, signed=False)

    # ---------- signed endpoints ----------
    def signed_get(self, path: str, params=None):
        return self._request('GET', path, params=params, signed=True)

    def signed_post(self, path: str, params=None):
        return self._request('POST', path, params=params, signed=True)
"@

Write-File "src\binance\spot_api.py" @"
from ..utils.symbols import spot_symbol

class SpotAPI:
    def __init__(self, client, quote_asset='USDT'):
        self.client = client
        self.quote_asset = quote_asset

    def exchange_info(self):
        return self.client.public_get('/api/v3/exchangeInfo')

    def ticker_price(self, symbol: str):
        return self.client.public_get('/api/v3/ticker/price', {'symbol': symbol})

    def account(self):
        return self.client.signed_get('/api/v3/account')

    def market_sell(self, coin: str, qty: float, quote: str = None):
        sym = spot_symbol(coin, quote or self.quote_asset)
        params = {
            'symbol': sym,
            'side': 'SELL',
            'type': 'MARKET',
            'quantity': qty,
            'newOrderRespType': 'FULL'
        }
        return self.client.signed_post('/api/v3/order', params)

    def market_buy_quote(self, coin: str, quote_qty: float, quote: str = None):
        sym = spot_symbol(coin, quote or self.quote_asset)
        params = {
            'symbol': sym,
            'side': 'BUY',
            'type': 'MARKET',
            'quoteOrderQty': quote_qty,
            'newOrderRespType': 'FULL'
        }
        return self.client.signed_post('/api/v3/order', params)
"@

Write-File "src\binance\convert_api.py" @"
import time

class ConvertAPI:
    def __init__(self, client):
        self.client = client

    def get_quote(self, from_asset: str, to_asset: str, from_amount=None, to_amount=None, walletType='SPOT', validTime='10s'):
        params = {
            'fromAsset': from_asset,
            'toAsset': to_asset,
            'fromAmount': from_amount,
            'toAmount': to_amount,
            'walletType': walletType,
            'validTime': validTime
        }
        return self.client.signed_post('/sapi/v1/convert/getQuote', params)

    def accept_quote(self, quote_id: str):
        return self.client.signed_post('/sapi/v1/convert/acceptQuote', {'quoteId': quote_id})

    def order_status(self, order_id=None, quote_id=None):
        return self.client.signed_get('/sapi/v1/convert/orderStatus', {'orderId': order_id, 'quoteId': quote_id})

    def convert_sell_to_usdt(self, coin: str, qty: float, timeout=5.0):
        quote = self.get_quote(from_asset=coin, to_asset='USDT', from_amount=qty)
        quote_id = quote.get('quoteId')
        if not quote_id:
            return None

        accept = self.accept_quote(quote_id)
        order_id = accept.get('orderId')
        if not order_id:
            return None

        t0 = time.time()
        while time.time() - t0 < timeout:
            st = self.order_status(order_id=order_id)
            if st and st.get('orderStatus') in ('SUCCESS', 'FAIL'):
                return st
            time.sleep(0.25)
        return None
"@

# ------------------------------------------------
# src/data
# ------------------------------------------------
Write-File "src\data\price_cache.py" @"
import time

class PriceCache:
    def __init__(self, spot_api, ttl_sec: float = 3.0):
        self.spot_api = spot_api
        self.ttl = ttl_sec
        self.cache = {}  # symbol -> (price, expire_ts)

    def get_last_price(self, symbol: str) -> float:
        now = time.time()
        item = self.cache.get(symbol)
        if item and item[1] > now:
            return item[0]

        data = self.spot_api.ticker_price(symbol)
        price = float(data['price'])
        self.cache[symbol] = (price, now + self.ttl)
        return price
"@

Write-File "src\data\spot_filters.py" @"
def build_spot_filters(exchange_info: dict) -> dict:
    \"\"\"
    Returns: { 'BTCUSDT': {'min_notional': float, 'step_size': float, 'min_qty': float} }
    \"\"\"
    out = {}
    for s in exchange_info.get('symbols', []):
        symbol = s.get('symbol')
        filters = {f.get('filterType'): f for f in s.get('filters', [])}

        lot = filters.get('LOT_SIZE', {})
        step = float(lot.get('stepSize', '0') or 0)
        min_qty = float(lot.get('minQty', '0') or 0)

        # Binance may use NOTIONAL or MIN_NOTIONAL depending on doc version.
        notional = filters.get('NOTIONAL') or filters.get('MIN_NOTIONAL') or {}
        min_notional = float(notional.get('minNotional', '0') or 0)

        out[symbol] = {
            'min_notional': min_notional,
            'step_size': step,
            'min_qty': min_qty
        }
    return out
"@
Write-File "src\data\convert_limits.py" @"
from ..utils.symbols import pair_key

def build_convert_limits() -> dict:
    \"\"\"
    Placeholder defaults.
    Convert API access is sometimes restricted; this keeps the bot functional.
    You can replace this with real fetching later (convert exchangeInfo/assetInfo).
    \"\"\"
    return {
        pair_key('BTC','USDT'): {'min_notional': 1.0, 'precision': 8},
        pair_key('ETH','USDT'): {'min_notional': 1.0, 'precision': 8},
        pair_key('SOL','USDT'): {'min_notional': 1.0, 'precision': 6},
    }
"@

# ------------------------------------------------
# src/engine - Accounting (WAC) + parsers
# ------------------------------------------------
Write-File "src\engine\accounting.py" @"
from ..utils.math_utils import floor_to_step, floor_to_precision

def apply_buy_fill(state: dict, coin: str, executed_qty: float, executed_quote_usdt: float, fee_usdt: float = 0.0, tag: str = 'BUY'):
    pos = state.setdefault('positions', {}).setdefault(coin, {'amount': 0.0, 'avg_price': 0.0})
    old_amt = float(pos.get('amount', 0.0))
    old_avg = float(pos.get('avg_price', 0.0))

    net_cost = executed_quote_usdt + fee_usdt
    new_amt = old_amt + executed_qty
    if new_amt <= 0:
        return

    new_avg = ((old_amt * old_avg) + net_cost) / new_amt
    pos['amount'] = new_amt
    pos['avg_price'] = new_avg

    state['cash_usdt'] = float(state.get('cash_usdt', 0.0)) - net_cost
    state['pnl']['fees_usdt'] = float(state['pnl'].get('fees_usdt', 0.0)) + fee_usdt

def apply_sell_fill_wac(state: dict, coin: str, executed_qty: float, executed_quote_usdt: float, fee_usdt: float = 0.0, tag: str = 'SELL', harvested: bool = False):
    pos = state.setdefault('positions', {}).setdefault(coin, {'amount': 0.0, 'avg_price': 0.0})
    avg_price = float(pos.get('avg_price', 0.0))

    cost_removed = executed_qty * avg_price
    net_proceeds = executed_quote_usdt - fee_usdt
    realized = net_proceeds - cost_removed

    pos['amount'] = float(pos.get('amount', 0.0)) - executed_qty
    state['cash_usdt'] = float(state.get('cash_usdt', 0.0)) + net_proceeds

    state['pnl']['realized_profit_usdt'] = float(state['pnl'].get('realized_profit_usdt', 0.0)) + realized
    state['pnl']['fees_usdt'] = float(state['pnl'].get('fees_usdt', 0.0)) + fee_usdt

    if harvested:
        state['pnl']['harvested_profit_usdt'] = float(state['pnl'].get('harvested_profit_usdt', 0.0)) + max(0.0, realized)
        pending = state['harvest']['pending_profit_target'].get(coin, 0.0)
        state['harvest']['pending_profit_target'][coin] = max(0.0, pending - max(0.0, realized))

def parse_spot_market_order(order: dict, fee_to_usdt_fn=None, fallback_base_asset=None, last_price_fn=None) -> tuple[float,float,float]:
    executed_qty = float(order.get('executedQty', 0.0))
    executed_quote = float(order.get('cummulativeQuoteQty', 0.0) or 0.0)

    fee_usdt = 0.0
    fills = order.get('fills') or []

    if executed_quote == 0.0 and fills:
        executed_quote = sum(float(f['price']) * float(f['qty']) for f in fills)

    for f in fills:
        commission = float(f.get('commission', 0.0))
        asset = (f.get('commissionAsset') or '').upper()
        if commission <= 0 or not asset:
            continue

        if fee_to_usdt_fn:
            val = fee_to_usdt_fn(asset, commission)
            if val is not None:
                fee_usdt += val
                continue

        # very rough fallback if fee asset == base asset and we have last price
        if last_price_fn and fallback_base_asset and asset == fallback_base_asset.upper():
            try:
                fee_usdt += commission * float(last_price_fn())
            except Exception:
                pass

    return executed_qty, executed_quote, fee_usdt
"@

# ------------------------------------------------
# src/engine - Momentum (placeholder)
# ------------------------------------------------
Write-File "src\engine\momentum.py" @"
def momentum_scores(prices_now: dict) -> dict:
    \"\"\"
    Placeholder momentum: returns 0 for all coins.
    Later you will replace with multi-horizon returns + z-score normalization.
    prices_now: {coin: price}
    \"\"\"
    return {k: 0.0 for k in prices_now.keys()}
"@

# ------------------------------------------------
# src/engine - Take profit logic (profit-target -> qty)
# ------------------------------------------------
Write-File "src\engine\take_profit.py" @"
def update_pending_profit_target(cfg: dict, state: dict, coin: str, price: float) -> float:
    pos = state.get('positions', {}).get(coin)
    if not pos:
        return 0.0

    amount = float(pos.get('amount', 0.0))
    avg_price = float(pos.get('avg_price', 0.0))
    profit = (price - avg_price) * amount
    if profit <= 0:
        return 0.0

    ratio = cfg['profit_take']['profit_harvest_ratio']
    add_target = profit * ratio
    pending = state['harvest']['pending_profit_target'].get(coin, 0.0) + add_target
    state['harvest']['pending_profit_target'][coin] = pending
    return pending

def compute_qty_to_realize_profit_target(cfg: dict, state: dict, coin: str, price: float) -> float:
    pos = state.get('positions', {}).get(coin)
    if not pos:
        return 0.0

    amount = float(pos.get('amount', 0.0))
    avg_price = float(pos.get('avg_price', 0.0))
    pending = float(state['harvest']['pending_profit_target'].get(coin, 0.0))

    if pending < cfg['profit_take']['min_profit_target_usdt']:
        return 0.0

    profit_per_coin = price - avg_price
    if profit_per_coin <= 0:
        return 0.0

    qty_needed = pending / profit_per_coin

    # safety cap: don't sell > X% of position value per cycle
    cap_ratio = cfg['profit_take']['max_sell_value_ratio_per_cycle']
    max_qty = (amount * cap_ratio)
    qty_needed = min(qty_needed, max_qty)

    qty_needed = min(qty_needed, amount)
    return max(0.0, qty_needed)
"@

# ------------------------------------------------
# src/engine - Dip buy placeholder (simple)
# ------------------------------------------------
Write-File "src\engine\dip_buy.py" @"
def decide_dip_buy(cfg: dict, state: dict, coin: str, price: float, momentum_z: float) -> float:
    if not cfg['dip_buy']['enabled']:
        return 0.0

    cash = float(state.get('cash_usdt', 0.0))
    min_buy = cfg['dip_buy']['min_buy_usdt']
    if cash < min_buy:
        return 0.0

    # optional momentum filter
    if cfg['dip_buy']['require_momentum_not_too_negative']:
        if momentum_z < cfg['dip_buy']['momentum_floor_z']:
            return 0.0

    # Buy only if price < avg_price (simple dip condition)
    pos = state.get('positions', {}).get(coin)
    if not pos:
        return 0.0
    avg_price = float(pos.get('avg_price', 0.0))
    if price >= avg_price:
        return 0.0

    # cap per cycle
    cap_ratio = cfg['dip_buy']['max_buy_value_ratio_per_cycle']
    max_spend = cash * cap_ratio
    spend = max(min_buy, min(max_spend, cash))
    return spend
"@

# ------------------------------------------------
# src/engine - Strategy (creates actions; NO API trading calls)
# ------------------------------------------------
Write-File "src\engine\strategy.py" @"
from ..utils.symbols import spot_symbol
from .momentum import momentum_scores
from .take_profit import update_pending_profit_target, compute_qty_to_realize_profit_target
from .dip_buy import decide_dip_buy

def decide_actions(cfg: dict, state: dict, log, price_cache=None) -> list:
    coins = cfg['portfolio']['coins']
    quote = cfg['portfolio']['quote_asset']

    # prices
    prices = {}
    if price_cache:
        for c in coins:
            sym = spot_symbol(c, quote)
            prices[c] = price_cache.get_last_price(sym)
    else:
        # if no cache provided, do nothing
        return []

    # momentum (placeholder)
    mom = momentum_scores(prices)

    actions = []
    for c in coins:
        price = prices[c]

        # update pending profit target
        if cfg['profit_take']['enabled']:
            pending = update_pending_profit_target(cfg, state, c, price)
            qty_tp = compute_qty_to_realize_profit_target(cfg, state, c, price)
            if qty_tp > 0:
                actions.append({'type': 'TAKE_PROFIT_SELL', 'coin': c, 'qty': qty_tp, 'price': price, 'pending': pending})

        # dip buy
        spend = decide_dip_buy(cfg, state, c, price, mom.get(c, 0.0))
        if spend > 0:
            actions.append({'type': 'DIP_BUY', 'coin': c, 'quote_qty': spend, 'price': price})

    return actions
"@

# ------------------------------------------------
# src/engine - Execution (Spot vs Convert routing + DRY_RUN)
# ------------------------------------------------
Write-File "src\engine\execution.py" @"
from ..utils.symbols import spot_symbol, pair_key
from ..utils.math_utils import floor_to_step, floor_to_precision
from .accounting import apply_sell_fill_wac, apply_buy_fill, parse_spot_market_order

def execute_actions(cfg: dict, state: dict, actions: list, log,
                    spot_api=None, convert_api=None,
                    spot_filters=None, convert_limits=None,
                    fee_to_usdt_fn=None, price_cache=None):
    dry_run = bool(cfg['bot'].get('dry_run', True))
    quote = cfg['portfolio']['quote_asset']

    results = []

    # simple cooldown tracking
    cooldown = int(cfg['portfolio']['max_trade_per_symbol_cooldown_sec'])
    last_trade_ts = state.setdefault('meta', {}).setdefault('last_trade_ts', {})

    import time as _time
    now = _time.time()

    for a in actions:
        coin = a['coin']
        # cooldown
        last = float(last_trade_ts.get(coin, 0.0))
        if now - last < cooldown:
            continue

        if a['type'] == 'TAKE_PROFIT_SELL':
            qty = float(a['qty'])
            if qty <= 0:
                continue

            sym = spot_symbol(coin, quote)
            f = (spot_filters or {}).get(sym, {'min_notional': 0.0, 'step_size': 0.0, 'min_qty': 0.0})
            min_notional = float(f.get('min_notional', 0.0))
            step_size = float(f.get('step_size', 0.0))
            min_qty = float(f.get('min_qty', 0.0))

            # step flooring (Spot)
            qty_spot = floor_to_step(qty, step_size) if step_size else qty
            notional = qty_spot * float(a.get('price', 0.0))

            # Convert fallback thresholds
            pk = pair_key(coin, quote)
            cl = (convert_limits or {}).get(pk, {'min_notional': 1.0, 'precision': 8})
            convert_min = float(cl.get('min_notional', 1.0))
            convert_prec = int(cl.get('precision', 8))

            if qty_spot < min_qty:
                continue

            if dry_run:
                log.info(f\"[DRY_RUN] SELL {coin} qty={qty_spot:.8f} notional~{notional:.2f}\")
                last_trade_ts[coin] = now
                results.append({'action': a, 'status': 'DRY_RUN'})
                continue

            # Route Spot vs Convert
            if notional >= min_notional and spot_api:
                order = spot_api.market_sell(coin, qty_spot, quote)
                exec_qty, exec_quote, fee_usdt = parse_spot_market_order(order, fee_to_usdt_fn=fee_to_usdt_fn)
                apply_sell_fill_wac(state, coin, exec_qty, exec_quote, fee_usdt, harvested=True)
                log.info(f\"SPOT SELL {coin}: +{exec_quote:.2f} {quote} fee~{fee_usdt:.4f} realized updated\")
                last_trade_ts[coin] = now
                results.append({'action': a, 'status': 'SPOT_OK'})
            elif notional >= convert_min and convert_api:
                qty_conv = floor_to_precision(qty, convert_prec)
                st = convert_api.convert_sell_to_usdt(coin, qty_conv)
                if not st or st.get('orderStatus') != 'SUCCESS':
                    log.warning(f\"CONVERT SELL {coin} failed/timeout\")
                    results.append({'action': a, 'status': 'CONVERT_FAIL'})
                else:
                    exec_qty = float(st['fromAmount'])
                    exec_quote = float(st['toAmount'])
                    apply_sell_fill_wac(state, coin, exec_qty, exec_quote, 0.0, harvested=True)
                    log.info(f\"CONVERT SELL {coin}: +{exec_quote:.2f} {quote} (spread implicit)\")
                    last_trade_ts[coin] = now
                    results.append({'action': a, 'status': 'CONVERT_OK'})
            else:
                results.append({'action': a, 'status': 'BELOW_MIN'})
            continue

        if a['type'] == 'DIP_BUY':
            quote_qty = float(a['quote_qty'])
            if quote_qty <= 0:
                continue

            if dry_run:
                log.info(f\"[DRY_RUN] BUY {coin} spend={quote_qty:.2f} {quote}\")
                last_trade_ts[coin] = now
                results.append({'action': a, 'status': 'DRY_RUN'})
                continue

            if spot_api:
                order = spot_api.market_buy_quote(coin, quote_qty, quote)
                # For buy: executedQty is base; cummulativeQuoteQty is quote spent
                exec_qty = float(order.get('executedQty', 0.0))
                exec_quote = float(order.get('cummulativeQuoteQty', 0.0) or quote_qty)
                # fee estimate from fills (optional)
                exec_qty2, exec_quote2, fee_usdt = parse_spot_market_order(order, fee_to_usdt_fn=fee_to_usdt_fn)
                apply_buy_fill(state, coin, exec_qty2, exec_quote2, fee_usdt)
                log.info(f\"SPOT BUY {coin}: qty={exec_qty2:.8f} cost={exec_quote2:.2f} fee~{fee_usdt:.4f}\")
                last_trade_ts[coin] = now
                results.append({'action': a, 'status': 'SPOT_OK'})
            continue

    return results
"@

# ------------------------------------------------
# src/engine - Reconcile (placeholder safe)
# ------------------------------------------------
Write-File "src\engine\reconcile.py" @"
def maybe_reconcile(cfg: dict, state: dict, log, spot_api=None):
    every = int(cfg['bot'].get('reconcile_every_cycles', 0))
    cycle = int(state.get('meta', {}).get('cycle', 0))
    if every <= 0 or cycle % every != 0:
        return

    if not spot_api:
        log.info('Reconcile skipped (no spot_api).')
        return

    try:
        acct = spot_api.account()
        balances = {b['asset']: float(b['free']) for b in acct.get('balances', [])}
        usdt = balances.get(cfg['portfolio']['quote_asset'], None)
        if usdt is not None:
            state['cash_usdt'] = float(usdt)
        log.info('Reconcile done (cash updated from account free balance).')
    except Exception as e:
        log.warning(f'Reconcile failed: {e}')
"@

# ------------------------------------------------
# src/main.py - continuous service loop
# ------------------------------------------------
Write-File "src\main.py" @"
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
"@

Write-Host "✅ Bootstrap content written successfully." -ForegroundColor Green
Write-Host "Next: run .\scripts\setup_venv.ps1 then .\scripts\run_bot.ps1" -ForegroundColor Cyan
