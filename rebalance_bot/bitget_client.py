"""
Thin wrapper around the Bitget REST API.

Handles HMAC-SHA256 request signing, error normalisation and the handful of
endpoints needed by the rebalance bot:

  * GET  /api/v2/spot/account/assets   – spot balances
  * GET  /api/v2/spot/market/tickers   – 24-h ticker (last price)
  * POST /api/v2/spot/trade/place-order – place a market order
"""

import hashlib
import hmac
import base64
import time
import logging
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.bitget.com"


class BitgetAPIError(Exception):
    """Raised when the Bitget API returns a non-zero result code."""


class BitgetClient:
    """Authenticated Bitget REST client."""

    def __init__(
        self,
        api_key: str = config.API_KEY,
        api_secret: str = config.API_SECRET,
        passphrase: str = config.API_PASSPHRASE,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_spot_balances(self) -> dict[str, float]:
        """Return {coin: available_balance} for every coin with balance > 0."""
        data = self._get("/api/v2/spot/account/assets")
        balances: dict[str, float] = {}
        for item in data:
            coin = item.get("coin", "")
            available = float(item.get("available", 0))
            if available > 0:
                balances[coin] = available
        return balances

    def get_price(self, symbol: str) -> Optional[float]:
        """Return the last traded price for *symbol* (e.g. ``"BTCUSDT"``).

        Returns ``None`` if the symbol is not found.
        """
        params = {"symbol": symbol}
        data = self._get("/api/v2/spot/market/tickers", params=params)
        if data:
            return float(data[0]["lastPr"])
        return None

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        quote_qty: Optional[float] = None,
    ) -> dict:
        """Place a spot market order.

        Args:
            symbol:    Trading pair, e.g. ``"BTCUSDT"``.
            side:      ``"buy"`` or ``"sell"``.
            quantity:  Base-asset quantity (used for sell orders).
            quote_qty: Quote-asset quantity (used for buy orders).
                       When provided ``quantity`` is ignored.

        Returns:
            The order object returned by the API.
        """
        body: dict = {
            "symbol": symbol,
            "side": side,
            "orderType": "market",
            "force": "gtc",
        }
        if side == "buy" and quote_qty is not None:
            body["size"] = str(round(quote_qty, 8))
            body["quoteSize"] = str(round(quote_qty, 8))
        else:
            body["size"] = str(round(quantity, 8))

        return self._post("/api/v2/spot/trade/place-order", body)

    # ------------------------------------------------------------------
    # Internal request helpers
    # ------------------------------------------------------------------

    def _sign(self, timestamp: str, method: str, path: str, body: str) -> str:
        message = f"{timestamp}{method.upper()}{path}{body}"
        mac = hmac.new(
            self._api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        )
        return base64.b64encode(mac.digest()).decode()

    def _auth_headers(self, method: str, path: str, body: str = "") -> dict:
        timestamp = str(int(time.time() * 1000))
        signature = self._sign(timestamp, method, path, body)
        return {
            "ACCESS-KEY": self._api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self._passphrase,
            "locale": "en-US",
        }

    def _get(self, path: str, params: Optional[dict] = None) -> list | dict:
        query = ""
        if params:
            query = "?" + "&".join(f"{k}={v}" for k, v in params.items())
        headers = self._auth_headers("GET", path + query)
        url = _BASE_URL + path
        response = self._session.get(url, params=params, headers=headers, timeout=10)
        return self._parse(response)

    def _post(self, path: str, body: dict) -> dict:
        import json

        body_str = json.dumps(body)
        headers = self._auth_headers("POST", path, body_str)
        url = _BASE_URL + path
        response = self._session.post(url, data=body_str, headers=headers, timeout=10)
        return self._parse(response)

    @staticmethod
    def _parse(response: requests.Response) -> list | dict:
        response.raise_for_status()
        payload = response.json()
        code = str(payload.get("code", "0"))
        if code != "00000":
            raise BitgetAPIError(
                f"API error {code}: {payload.get('msg', 'unknown error')}"
            )
        return payload.get("data", {})
