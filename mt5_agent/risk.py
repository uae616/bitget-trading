from __future__ import annotations

from datetime import datetime, timezone

from .config import RiskConfig


class RiskGuard:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def within_trading_window(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        current = now.time()
        return self.config.trade_start <= current <= self.config.trade_end

    def drawdown_ok(self, balance: float, equity: float) -> bool:
        if balance <= 0:
            return False
        drawdown_pct = ((balance - equity) / balance) * 100.0
        return drawdown_pct <= self.config.max_daily_drawdown_pct

    def calculate_volume(self, balance: float, stop_distance_points: float, point_value: float, min_volume: float, volume_step: float, max_volume: float | None = None) -> float:
        if stop_distance_points <= 0 or point_value <= 0:
            return min_volume
        risk_amount = balance * (self.config.risk_per_trade_pct / 100.0)
        raw_volume = risk_amount / (stop_distance_points * point_value)
        stepped = max(min_volume, round(raw_volume / volume_step) * volume_step)
        if max_volume is not None and max_volume > 0:
            stepped = min(stepped, max_volume)
        return round(stepped, 8)
