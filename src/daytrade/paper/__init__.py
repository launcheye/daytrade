"""Paper-trading engine — the only (simulation-only) broker in the platform."""

from __future__ import annotations

from .broker import PaperBroker, TradeRecord

__all__ = ["PaperBroker", "TradeRecord"]
