from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from .logging_utils import AuditLogger
from .mt5_client import MT5Client
from .types import TradeRequest, TradeResult
from .validation import _to_mt5_request


class ExecutionAdapter:
    def __init__(self, client: MT5Client, max_retries: int, audit_logger: AuditLogger) -> None:
        self.client = client
        self.max_retries = max_retries
        self.audit_logger = audit_logger
        self._seen_idempotency_keys: set[str] = set()

    def execute(self, request: TradeRequest) -> TradeResult:
        key = _build_idempotency_key(request)
        if key in self._seen_idempotency_keys:
            return TradeResult(
                request_id=request.request_id,
                accepted=False,
                code=-2,
                message="Duplicate request blocked by idempotency key",
            )

        payload = _to_mt5_request(request)
        self.audit_logger.write("trade.request", {"request": payload, "request_id": request.request_id})

        for attempt in range(1, self.max_retries + 1):
            result = self.client.order_send(payload)
            if result is None:
                if attempt < self.max_retries:
                    time.sleep(min(0.5 * attempt, 2))
                    if not self.client.health_check():
                        self.client.reconnect()
                    continue
                return TradeResult(request.request_id, False, -1, "No response from terminal")

            retcode = int(getattr(result, "retcode", -1))
            comment = str(getattr(result, "comment", ""))
            order_id = getattr(result, "order", None)
            self.audit_logger.write(
                "trade.response",
                {
                    "request_id": request.request_id,
                    "retcode": retcode,
                    "comment": comment,
                    "order_id": order_id,
                    "attempt": attempt,
                },
            )

            if retcode == 10009:
                self._seen_idempotency_keys.add(key)
                return TradeResult(request.request_id, True, retcode, comment, int(order_id or 0))

            if attempt < self.max_retries:
                time.sleep(min(0.5 * attempt, 2))
                if not self.client.health_check():
                    self.client.reconnect()
                continue

            return TradeResult(request.request_id, False, retcode, comment, int(order_id or 0))

        return TradeResult(request.request_id, False, -1, "Retries exhausted")


def _build_idempotency_key(request: TradeRequest) -> str:
    digest_src = {
        "request_id": request.request_id,
        "symbol": request.symbol,
        "side": request.side,
        "volume": request.volume,
        "price": request.price,
        "sl": request.stop_loss,
        "tp": request.take_profit,
    }
    encoded = json.dumps(digest_src, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
