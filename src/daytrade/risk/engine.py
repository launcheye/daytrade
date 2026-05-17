"""Risk engine — sizing, loss limits and realistic fill execution.

The risk engine sits between a *decision* and an *execution*. It answers three
questions, in order:

1. Are we allowed to trade right now? (daily-loss circuit breaker)
2. If so, how big? (risk-based position sizing)
3. What fill do we actually get? (adverse fees / slippage / partial fill)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..config.schema import RiskConfig
from ..models import Fill, Side
from .execution import simulate_fill
from .limits import DailyLossTracker
from .sizing import SizingResult, position_size


@dataclass(frozen=True)
class TradePermission:
    """Whether a new entry is currently permitted."""

    allowed: bool
    reason: str


class RiskEngine:
    """Stateful risk controller for a single trading session."""

    def __init__(self, config: RiskConfig, starting_equity: float) -> None:
        self.config = config
        self._loss_tracker = DailyLossTracker(
            starting_equity, config.max_daily_loss_pct
        )

    def observe_equity(self, timestamp: datetime, equity: float) -> None:
        """Feed the latest equity to the daily-loss tracker (call per bar)."""
        self._loss_tracker.observe(timestamp, equity)

    def permission(self, equity: float) -> TradePermission:
        """Check whether a new entry is allowed given current ``equity``."""
        if self._loss_tracker.is_breached(equity):
            loss = self._loss_tracker.loss_pct(equity)
            return TradePermission(
                allowed=False,
                reason=(
                    f"daily loss limit hit: down {loss * 100:.2f}% "
                    f">= {self.config.max_daily_loss_pct * 100:.2f}%"
                ),
            )
        return TradePermission(allowed=True, reason="within risk limits")

    def size(self, equity: float, entry: float, stop: float) -> SizingResult:
        """Risk-based position size for a planned entry/stop."""
        return position_size(equity, entry, stop, self.config)

    def execute(
        self,
        order_id: str,
        symbol: str,
        side: Side,
        quantity: float,
        reference_price: float,
        available_liquidity: float,
        timestamp: Optional[datetime] = None,
    ) -> Fill:
        """Simulate an adverse, realistic fill for an order."""
        return simulate_fill(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            reference_price=reference_price,
            available_liquidity=available_liquidity,
            config=self.config,
            timestamp=timestamp,
        )

    @property
    def daily_loss_tracker(self) -> DailyLossTracker:
        return self._loss_tracker
