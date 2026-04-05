import time
import hmac
import hashlib
import urllib.parse
import base64
import requests

from ..core.errors import BotError
from ..core.clock import TimeSync


class BitgetAPIError(BotError):
    def __init__(self, status_code: int, payload: str):
        super().__init__(f"Bitget API error {status_code}: {payload}")
        self.status_code = status_code
        self.payload = payload


class BitgetRestClient:
    """
    Bitget REST API client with HMAC-SHA256 signature authentication.
    https://www.bitget.com/api-docs/spot/intro
    
    Bitget requires:
    - API Key
    - API Secret
    - Passphrase (for auth header)
    - Timestamp (milliseconds)
    - Signature: HMAC-SHA256(timestamp + method + request_path + body, api_secret)
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
        base_url: str = 'https://api.bitget.com',
        timeout: int = 10
    ):
        self.api_key = api_key or ''
        self.api_secret = api_secret or ''
        self.api_passphrase = api_passphrase or ''
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        
        # Disable automatic decompression to handle it manually
        # This helps with gzip/brotli responses
        self.session.trust_env = True
        
        # Set headers on session to persist across requests
        # These headers help bypass Cloudflare WAF protection
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Origin': 'https://www.bitget.com',
            'Referer': 'https://www.bitget.com/',
            'Sec-CH-UA': '"Not_A Brand";v="8", "Chromium";v="120"',
            'Sec-CH-UA-Mobile': '?0',
            'Sec-CH-UA-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
        })
        self.clock = TimeSync()

    # ---------- low-level helpers ----------
    def _get_timestamp_ms(self) -> int:
        """Get current timestamp in milliseconds (synced with server)."""
        return self.clock.now_ms() if self.clock else int(time.time() * 1000)

    def _sign(self, message: str) -> str:
        """Generate HMAC-SHA256 signature."""
        return base64.b64encode(
            hmac.new(
                self.api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')

    def _request(
        self,
        method: str,
        path: str,
        params=None,
        body=None,
        signed=False,
        retries: int = 2
    ):
        """
        Core request handler.
        
        For signed requests:
        - GET: signature based on timestamp + method + path + ""
        - POST: signature based on timestamp + method + path + json_body
        """
        url = f"{self.base_url}{path}"
        headers = {
            'Content-Type': 'application/json',
        }

        if self.api_key:
            headers['X-BITGET-APIKEY'] = self.api_key
            headers['X-BITGET-PASSPHRASE'] = self.api_passphrase

        if signed:
            timestamp_ms = str(self._get_timestamp_ms())
            
            # Build message for signature: timestamp + method + path + body
            if method.upper() == 'GET':
                # For GET requests, build query string from params
                query_string = ''
                if params:
                    params = {k: v for k, v in params.items() if v is not None}
                    query_string = urllib.parse.urlencode(params)
                    url = f"{url}?{query_string}"
                message = timestamp_ms + method.upper() + path + (f"?{query_string}" if query_string else "")
            else:
                # For POST requests, use JSON body
                import json
                body_str = json.dumps(body) if body else ''
                message = timestamp_ms + method.upper() + path + body_str
            
            signature = self._sign(message)
            headers['X-BITGET-SIGN'] = signature
            headers['X-BITGET-TIMESTAMP'] = timestamp_ms
        else:
            # For unsigned requests, params go in URL
            if params:
                params = {k: v for k, v in params.items() if v is not None}
                query_string = urllib.parse.urlencode(params)
                url = f"{url}?{query_string}"

        last_exc = None
        for attempt in range(retries + 1):
            try:
                if method.upper() in ['POST', 'PUT']:
                    import json
                    r = self.session.request(
                        method.upper(),
                        url,
                        headers=headers,
                        json=body if body else None,
                        timeout=self.timeout
                    )
                else:
                    r = self.session.request(
                        method.upper(),
                        url,
                        headers=headers,
                        timeout=self.timeout
                    )

                if r.status_code >= 400:
                    # Try to get readable error message
                    error_text = None
                    
                    # Try to decode the response (may be gzip compressed)
                    try:
                        # First try JSON
                        error_data = r.json()
                        error_text = str(error_data)
                    except Exception:
                        pass
                    
                    if not error_text:
                        try:
                            # Try to decompress if gzipped
                            import gzip
                            decompressed = gzip.decompress(r.content).decode('utf-8')
                            error_text = decompressed[:500]  # Limit length
                        except Exception:
                            pass
                    
                    if not error_text:
                        try:
                            # Try plain text
                            error_text = r.text[:500]
                        except Exception:
                            error_text = f"[Binary response - status {r.status_code}]"
                    
                    raise BitgetAPIError(r.status_code, error_text)
                
                return r.json()
            except Exception as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(0.5)

        raise last_exc

    # ---------- public endpoints ----------
    def ping(self):
        """Health check endpoint."""
        return self._request('GET', '/v2/public/time', signed=False)

    def server_time(self):
        """Get server time in milliseconds."""
        resp = self._request('GET', '/v2/public/time', signed=False)
        # Bitget returns {"serverTime": "1234567890123", "data": {...}}
        if 'serverTime' in resp:
            return int(resp['serverTime'])
        if 'data' in resp and 'serverTime' in resp['data']:
            return int(resp['data']['serverTime'])
        return None

    def sync_time(self):
        """Sync local clock with server."""
        server_time_ms = self.server_time()
        if server_time_ms:
            self.clock.set_offset(server_time_ms)
        return server_time_ms

    def public_get(self, path: str, params=None):
        """Generic unsigned GET request."""
        return self._request('GET', path, params=params, signed=False)

    # ---------- signed endpoints ----------
    def signed_get(self, path: str, params=None):
        """Generic signed GET request."""
        return self._request('GET', path, params=params, signed=True)

    def signed_post(self, path: str, body=None):
        """Generic signed POST request."""
        return self._request('POST', path, body=body, signed=True)

    def signed_put(self, path: str, body=None):
        """Generic signed PUT request."""
        return self._request('PUT', path, body=body, signed=True)
