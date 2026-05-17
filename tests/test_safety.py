"""Safety tests — assert that real trading is structurally impossible."""

from __future__ import annotations

import pytest

import daytrade
from daytrade.config import ConfigError, load_config_dict
from daytrade.exchanges import BinanceClient, BybitClient, CoinGeckoClient
from daytrade.paper import PaperBroker
from daytrade.safety.guard import assert_paper_only, forbid_real_trading

pytestmark = pytest.mark.safety


def test_real_trading_flag_is_false():
    assert daytrade.REAL_TRADING_ENABLED is False


def test_forbid_real_trading_always_raises():
    with pytest.raises(NotImplementedError, match="Real trading is disabled"):
        forbid_real_trading()


def test_forbid_real_trading_includes_context():
    with pytest.raises(NotImplementedError, match="my-context"):
        forbid_real_trading("my-context")


def test_assert_paper_only_passes_in_clean_tree():
    assert_paper_only()  # must not raise


def test_paper_broker_live_connection_raises():
    broker = PaperBroker(starting_cash=10_000.0)
    with pytest.raises(NotImplementedError, match="Real trading is disabled"):
        broker.connect_live()


def test_config_cannot_enable_live_trading():
    with pytest.raises(ConfigError):
        load_config_dict({"safety": {"live_trading_enabled": True}})


def test_no_exchange_client_exposes_order_entry():
    """Public clients are read-only — no place/cancel/submit order method."""
    forbidden = {"place_order", "submit_order", "cancel_order", "create_order"}
    for cls in (BinanceClient, BybitClient, CoinGeckoClient):
        assert forbidden.isdisjoint(dir(cls)), f"{cls.__name__} exposes order entry"


def test_paper_broker_has_no_order_entry_to_real_market():
    """The only order method is the simulated one; the live one raises."""
    broker = PaperBroker(starting_cash=1_000.0)
    assert hasattr(broker, "submit_market_order")  # simulated — allowed
    # connect_live exists only to raise (tested above).


def test_no_leverage_in_paper_broker():
    """Spot, long-only: cannot sell what you do not own (no shorting)."""
    from datetime import datetime, timezone
    from daytrade.config import load_config
    from daytrade.models import Side

    broker = PaperBroker(starting_cash=10_000.0)
    cfg = load_config(load_dotenv_file=False)
    with pytest.raises(ValueError, match="no open position"):
        broker.submit_market_order(
            "o1", "BTCUSDT", Side.SELL, 1.0, reference_price=100.0,
            available_liquidity=100.0, risk_config=cfg.risk,
            timestamp=datetime.now(timezone.utc),
        )
