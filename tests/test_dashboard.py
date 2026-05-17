"""Dashboard backend tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from daytrade.config import WatchlistConfig, load_config
from daytrade.dashboard import create_app
from daytrade.observatory import LiveMockFeed, ObservatoryDB, Observer

_T0 = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)


def _populated_db(tmp_path):
    db_path = tmp_path / "obs.db"
    obs = Observer(load_config(load_dotenv_file=False),
                   WatchlistConfig(symbols=["BTCUSDT", "ETHUSDT"]),
                   db=ObservatoryDB(db_path), feed=LiveMockFeed())
    obs.start()
    for k in range(3):
        obs.run_once(_T0 + timedelta(minutes=20 * k))
    obs.run_once(_T0 + timedelta(minutes=120))
    obs.stop()
    obs.db.close()
    return db_path


def test_dashboard_serves_index(tmp_path):
    client = TestClient(create_app(tmp_path / "empty.db"))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Market Safety Observatory" in resp.text


def test_dashboard_health_is_paper_only(tmp_path):
    client = TestClient(create_app(tmp_path / "empty.db"))
    body = client.get("/api/health").json()
    assert body["real_trading"] is False
    assert body["paper_only"] is True


def test_dashboard_overview_returns_data(tmp_path):
    client = TestClient(create_app(_populated_db(tmp_path)))
    body = client.get("/api/overview").json()
    assert "safety_score" in body
    assert body["symbols_observed"] == 2
    assert "status" in body and "condition" in body


def test_dashboard_symbols_endpoint(tmp_path):
    client = TestClient(create_app(_populated_db(tmp_path)))
    rows = client.get("/api/symbols").json()
    assert isinstance(rows, list) and len(rows) == 2
    assert {"symbol", "price", "trend", "safety_score", "status"} <= set(rows[0])


def test_dashboard_symbol_detail(tmp_path):
    client = TestClient(create_app(_populated_db(tmp_path)))
    body = client.get("/api/symbol/BTCUSDT").json()
    assert body["symbol"] == "BTCUSDT"
    assert len(body["series"]) > 0
    assert len(body["predictions"]) > 0


def test_dashboard_accuracy_paper_risk(tmp_path):
    client = TestClient(create_app(_populated_db(tmp_path)))
    for endpoint in ("/api/accuracy", "/api/paper", "/api/risk",
                     "/api/safety-history"):
        resp = client.get(endpoint)
        assert resp.status_code == 200
        assert resp.json() is not None


def test_dashboard_empty_db_does_not_crash(tmp_path):
    """The dashboard works against a brand-new, empty database."""
    client = TestClient(create_app(tmp_path / "fresh.db"))
    overview = client.get("/api/overview").json()
    assert overview["symbols_observed"] == 0
    assert client.get("/api/symbols").json() == []
