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
        url = f"{self.base_url}{path}"
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
            full_query = f"{query}&signature={sig}" if query else f"signature={sig}"
            url = f"{url}?{full_query}"
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

