from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .logging_utils import AuditLogger
from .mt5_client import MT5Client
from .mt5_payload import to_mt5_request
from .types import TradeRequest, TradeResult


class ExecutionAdapter:
    def __init__(self, client: MT5Client, max_retries: int, audit_logger: AuditLogger, idempotency_store_path: str = ".idempotency_keys") -> None:
        self.client = client
        self.max_retries = max_retries
        self.audit_logger = audit_logger
        self._idempotency_store = Path(idempotency_store_path)
        self._idempotency_store.parent.mkdir(parents=True, exist_ok=True)
        self._seen_idempotency_keys: set[str] = set()
        if self._idempotency_store.exists():
            self._seen_idempotency_keys = {line.strip() for line in self._idempotency_store.read_text(encoding="utf-8").splitlines() if line.strip()}

    def execute(self, request: TradeRequest) -> TradeResult:
        key = _build_idempotency_key(request)
        if key in self._seen_idempotency_keys:
            return TradeResult(
                request_id=request.request_id,
                accepted=False,
                code=-2,
                message="Duplicate request blocked by idempotency key",
            )

        payload = to_mt5_request(request)
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
                with self._idempotency_store.open("a", encoding="utf-8") as fp:
                    fp.write(key + "\n")
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
