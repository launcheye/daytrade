"""Exchange infrastructure — read-only market data, consensus, failover.

There is no order-entry code anywhere in this package. Data comes in; orders
never go out.
"""

from __future__ import annotations

from .base import ExchangeError, MarketDataClient
from .consensus import compute_consensus
from .mock import MockExchange, build_orderbook, generate_random_walk
from .provider import MarketDataProvider, build_provider
from .public import (
    BinanceClient,
    BybitClient,
    CoinGeckoClient,
    build_public_client,
)

__all__ = [
    "MarketDataClient",
    "ExchangeError",
    "MockExchange",
    "generate_random_walk",
    "build_orderbook",
    "compute_consensus",
    "MarketDataProvider",
    "build_provider",
    "BinanceClient",
    "BybitClient",
    "CoinGeckoClient",
    "build_public_client",
]
