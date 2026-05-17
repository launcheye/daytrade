"""Loss-limit tracking — the daily circuit breaker.

A max-daily-loss limit is a behavioural safeguard: once the day's drawdown
breaches the threshold, no new entries are allowed until the next session.
It cannot prevent a loss already taken — it stops the bleeding from
compounding.
"""

from __future__ import annotations

from datetime import date, datetime


class DailyLossTracker:
    """Tracks intraday drawdown against a per-day equity high-water start."""

    def __init__(self, starting_equity: float, max_daily_loss_pct: float) -> None:
        if starting_equity <= 0:
            raise ValueError("starting_equity must be > 0")
        self._max_loss_pct = max_daily_loss_pct
        self._day: date | None = None
        self._day_start_equity = starting_equity

    def observe(self, timestamp: datetime, equity: float) -> None:
        """Record equity at ``timestamp``, rolling the day window if needed."""
        day = timestamp.date()
        if self._day is None or day != self._day:
            self._day = day
            self._day_start_equity = equity

    def loss_pct(self, equity: float) -> float:
        """Current day's loss as a positive fraction (0 if flat or up)."""
        if self._day_start_equity <= 0:
            return 0.0
        change = (equity - self._day_start_equity) / self._day_start_equity
        return max(0.0, -change)

    def is_breached(self, equity: float) -> bool:
        """True once the day's loss meets or exceeds the configured limit."""
        return self.loss_pct(equity) >= self._max_loss_pct

    @property
    def day_start_equity(self) -> float:
        return self._day_start_equity
