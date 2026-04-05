import time
import math

from unified_scanner.signal_scorer import score_signal
from unified_scanner.sl_tp import compute_sl_tp


class KlineScanner:
    """
    Scanner that fetches klines and produces a snapshot of prices + momentum features.
    Read-only: no trading, no accounting updates.
    """

    def __init__(self, spot_api, quote_asset="USDT", interval="15m", limit=120, ttl_sec=20):
        self.spot_api = spot_api
        self.quote_asset = quote_asset
        self.interval = interval
        self.limit = limit
        self.ttl_sec = ttl_sec
        # cache: (symbol, interval) -> {"ts":..., "klines":[...], "last_open":...}
        self._cache = {}

    def _spot_symbol(self, coin: str) -> str:
        return f"{coin.upper()}{self.quote_asset.upper()}"

    def _fetch_klines(self, symbol: str) -> list:
        # SpotAPI must implement: klines(symbol, interval, limit)
        return self.spot_api.klines(symbol, self.interval, self.limit)

    def get_klines(self, coin: str) -> list:
        symbol = self._spot_symbol(coin)
        key = (symbol, self.interval)

        now = time.time()
        cached = self._cache.get(key)

        if cached and (now - cached["ts"] < self.ttl_sec):
            return cached["klines"]

        kl = self._fetch_klines(symbol)
        last_open = int(kl[-1][0]) if kl else 0

        self._cache[key] = {"ts": now, "klines": kl, "last_open": last_open}
        return kl

    @staticmethod
    def _close_prices(klines: list) -> list:
        # Binance kline format: [ openTime, open, high, low, close, volume, closeTime, ... ]
        return [float(k[4]) for k in klines]

    @staticmethod
    def _pct_return(now_price: float, past_price: float) -> float:
        if past_price <= 0:
            return 0.0
        return (now_price - past_price) / past_price

    @staticmethod
    def _stdev(values: list) -> float:
        if len(values) < 2:
            return 0.0
        m = sum(values) / len(values)
        var = sum((x - m) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(var)

    def scan(self, coins: list, horizons: dict, weights: dict) -> dict:
        """
        horizons example (15m candles):
          {"30m": 2, "4h": 16, "1d": 96}
        weights:
          {"30m": 0.5, "4h": 0.3, "1d": 0.2}
        """
        ts_ms = int(time.time() * 1000)

        prices = {}
        returns = {}
        momentum_raw = {}
        volatility = {}

        for coin in coins:
            kl = self.get_klines(coin)
            closes = self._close_prices(kl)

            if len(closes) < max(horizons.values()) + 1:
                continue

            last = closes[-1]
            prices[coin] = last

            # multi-horizon returns
            r = {}
            for name, bars_back in horizons.items():
                past = closes[-1 - bars_back]
                r[name] = self._pct_return(last, past)
            returns[coin] = r

            # weighted momentum
            m = 0.0
            for name, w in weights.items():
                m += w * r.get(name, 0.0)
            momentum_raw[coin] = m

            # volatility: stdev of recent 1-bar returns
            rets = []
            for i in range(1, 50):
                rets.append(self._pct_return(closes[-i], closes[-i - 1]))
            volatility[coin] = self._stdev(rets)

        mz = self._zscore_dict(momentum_raw)

        return {
            "ts": ts_ms,
            "prices": prices,
            "returns": returns,
            "momentum_raw": momentum_raw,
            "momentum_z": mz,
            "volatility": volatility,
            "interval": self.interval,
            "limit": self.limit,
        }

    @staticmethod
    def _zscore_dict(scores: dict) -> dict:
        vals = list(scores.values())
        if not vals:
            return {}
        mean = sum(vals) / len(vals)
        var = sum((x - mean) ** 2 for x in vals) / max(1, len(vals) - 1)
        std = math.sqrt(var) if var > 0 else 1.0
        return {k: (v - mean) / std for k, v in scores.items()}

    # ------------------------------------------------------------------
    # full_scan: enhanced scan with all indicators, scoring, and SL/TP
    # ------------------------------------------------------------------

    def full_scan(self, coins: list, horizons: dict, weights: dict, scanner_cfg: dict | None = None) -> dict:
        """
        Extended scan that returns everything scan() does, PLUS per-coin:
          - signal: SignalResult (direction, score, confidence, reasons, indicators)
          - sl_tp: SlTpResult (stop_loss, take_profit, trailing_stop, atr)

        Backward compatible: all original keys are present unchanged.
        """
        # First get the base snapshot (prices, returns, momentum, volatility)
        snapshot = self.scan(coins, horizons, weights)
        mz = snapshot.get("momentum_z", {})

        signals = {}
        sl_tp = {}

        for coin in coins:
            if coin not in snapshot.get("prices", {}):
                continue

            kl = self.get_klines(coin)
            if len(kl) < 50:
                continue

            cfg = scanner_cfg or {}
            sig = score_signal(kl, cfg, momentum_z=mz.get(coin, 0.0))
            signals[coin] = sig

            if sig.direction != "HOLD":
                sl_tp[coin] = compute_sl_tp(kl, sig.direction, cfg)

        snapshot["signals"] = signals
        snapshot["sl_tp"] = sl_tp
        return snapshot
