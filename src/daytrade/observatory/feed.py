"""Continuous, time-driven market feed for the observatory.

The observer runs forever, so it needs market data that *advances with the
wall clock* and is identical across restarts. ``LiveMockFeed`` provides that:
price is a pure deterministic function of ``(symbol, absolute-minute)`` — a
blend of sinusoidal cycles plus hash-based noise. Because it is a function of
absolute time, a prediction made at T can be honestly evaluated at T+H by
sampling the feed at T+H, and a crashed-and-restarted observer sees exactly
the same history.

Each watchlist symbol has a distinct *profile* so the dashboard shows a
realistic mix of regimes — calm, choppy, volatile, panicky.

This feed is SIMULATED. No network, no real prices, no orders.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from ..exchanges.mock import build_orderbook
from ..models import OHLCV, OrderBookSnapshot, PriceTick

# Absolute time origin for the minute index.
_EPOCH = datetime(2025, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class SymbolProfile:
    """Deterministic market character for one simulated symbol."""

    base_price: float
    volume_24h_usd: float
    spread_bps: float
    book_base_qty: float
    book_depth: int
    trend_amp: float        # slow ~1-day swing amplitude (log units)
    cycle_amp: float        # medium ~2h cycle amplitude
    chop_amp: float         # fast ~15min wobble amplitude
    noise: float            # per-minute random amplitude


# Eight watchlist majors, each with a deliberately different character.
_PROFILES: Dict[str, SymbolProfile] = {
    "BTCUSDT":  SymbolProfile(62_000.0, 2.4e10, 2.0, 1.2, 20, 0.020, 0.008, 0.0020, 0.0009),
    "ETHUSDT":  SymbolProfile(3_050.0, 1.1e10, 2.5, 22.0, 20, 0.024, 0.010, 0.0030, 0.0012),
    "SOLUSDT":  SymbolProfile(152.0, 3.2e9, 3.5, 430.0, 20, 0.030, 0.014, 0.0060, 0.0020),
    "BNBUSDT":  SymbolProfile(585.0, 9.0e8, 3.0, 120.0, 20, 0.016, 0.006, 0.0018, 0.0008),
    "XRPUSDT":  SymbolProfile(0.62, 8.0e8, 4.0, 1.1e5, 20, 0.018, 0.020, 0.0140, 0.0030),
    "DOGEUSDT": SymbolProfile(0.155, 7.0e8, 5.0, 4.5e5, 20, 0.040, 0.028, 0.0180, 0.0050),
    "AVAXUSDT": SymbolProfile(36.0, 4.0e8, 4.5, 1900.0, 20, 0.034, 0.018, 0.0090, 0.0030),
    "LINKUSDT": SymbolProfile(18.5, 3.5e8, 4.0, 3600.0, 20, 0.022, 0.012, 0.0050, 0.0018),
}

_DEFAULT_PROFILE = SymbolProfile(25.0, 2.0e8, 5.0, 5_000.0, 20,
                                 0.020, 0.012, 0.0060, 0.0020)


def profile_for(symbol: str) -> SymbolProfile:
    return _PROFILES.get(symbol.upper(), _DEFAULT_PROFILE)


def known_symbols() -> List[str]:
    return list(_PROFILES)


def _hash_unit(key: str) -> float:
    """Deterministic value in [-1, 1] from a string key."""
    digest = hashlib.md5(key.encode()).digest()
    raw = int.from_bytes(digest[:8], "big")
    return (raw / float(1 << 64)) * 2.0 - 1.0


def minute_index(when: datetime) -> int:
    """Whole minutes from the fixed epoch to ``when``."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return int((when - _EPOCH).total_seconds() // 60)


class LiveMockFeed:
    """A deterministic, restart-safe simulated market feed."""

    def price_at(self, symbol: str, when: datetime) -> float:
        """The (deterministic) simulated price of ``symbol`` at ``when``."""
        return self._price_at_minute(symbol, minute_index(when))

    def _price_at_minute(self, symbol: str, m: int) -> float:
        p = profile_for(symbol)
        phase = _hash_unit(f"{symbol}:phase") * math.pi
        # Layered sinusoids: slow trend + medium cycle + fast chop.
        log_offset = (
            p.trend_amp * math.sin(2 * math.pi * m / 1440.0 + phase)
            + p.cycle_amp * math.sin(2 * math.pi * m / 137.0 + 2 * phase)
            + p.chop_amp * math.sin(2 * math.pi * m / 17.0 + 3 * phase)
            + p.noise * _hash_unit(f"{symbol}:{m}")
        )
        return p.base_price * math.exp(log_offset)

    def candles_at(self, symbol: str, as_of: datetime,
                   n_bars: int = 300) -> List[OHLCV]:
        """The ``n_bars`` 1-minute candles ending at ``as_of``."""
        end_m = minute_index(as_of)
        candles: List[OHLCV] = []
        for m in range(end_m - n_bars + 1, end_m + 1):
            close = self._price_at_minute(symbol, m)
            open_ = self._price_at_minute(symbol, m - 1)
            wick = abs(_hash_unit(f"{symbol}:wick:{m}")) * 0.0008
            hi = max(open_, close) * (1.0 + wick)
            lo = min(open_, close) * (1.0 - wick)
            vol = 800.0 + abs(_hash_unit(f"{symbol}:vol:{m}")) * 600.0
            ts = _EPOCH + timedelta(minutes=m)
            candles.append(OHLCV(
                symbol=symbol, timestamp=ts,
                open=round(open_, 8), high=round(hi, 8),
                low=round(lo, 8), close=round(close, 8),
                volume=round(vol, 4)))
        return candles

    def orderbook_at(self, symbol: str, as_of: datetime) -> OrderBookSnapshot:
        """A simulated L2 orderbook for ``symbol`` at ``as_of``."""
        p = profile_for(symbol)
        m = minute_index(as_of)
        price = self._price_at_minute(symbol, m)
        # Imbalance drifts deterministically with time.
        imbalance = 0.35 * _hash_unit(f"{symbol}:imb:{m // 3}")
        return build_orderbook(
            symbol=symbol, mid_price=price, exchange="observatory",
            depth=p.book_depth, spread_bps=p.spread_bps,
            base_quantity=p.book_base_qty, imbalance=imbalance,
            timestamp=_EPOCH + timedelta(minutes=m), jitter=0.0)

    def tick_at(self, symbol: str, as_of: datetime) -> PriceTick:
        p = profile_for(symbol)
        m = minute_index(as_of)
        return PriceTick(
            symbol=symbol, exchange="observatory",
            price=self._price_at_minute(symbol, m),
            timestamp=_EPOCH + timedelta(minutes=m),
            volume_24h=p.volume_24h_usd)
