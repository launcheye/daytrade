"""Dashboard data assembly.

Turns the observatory database into the JSON payloads the dashboard pages
consume. Every accessor is defensive — an empty or freshly-created database
yields sensible empty/default structures rather than errors, so the dashboard
works even before the observer has run.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..observatory.database import DEFAULT_DB_PATH, ObservatoryDB
from ..observatory.prediction_tracker import build_prediction_memory

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LATEST_CYCLE = _REPO_ROOT / "reports" / "observer" / "latest.json"

# A heartbeat older than this means the observer is not considered "live".
_HEARTBEAT_STALE_SECONDS = 1200.0
_STARTING_CASH = 10_000.0


def _json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def _trend_label(slope: Optional[float]) -> str:
    if slope is None:
        return "flat"
    if slope > 0.0004:
        return "up"
    if slope < -0.0004:
        return "down"
    return "flat"


def _drawdown(closed: List[Dict[str, Any]]) -> Dict[str, float]:
    """Equity curve + max drawdown from closed paper trades."""
    equity = _STARTING_CASH
    peak = equity
    max_dd = 0.0
    ordered = sorted(closed, key=lambda t: t.get("ts_close") or "")
    for trade in ordered:
        equity += trade.get("pnl") or 0.0
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
    return {"equity": round(equity, 2), "peak": round(peak, 2),
            "max_drawdown_pct": round(max_dd * 100, 2)}


class DashboardData:
    """Read-only data accessor for the dashboard backend."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db = ObservatoryDB(db_path)

    # -- pages ---------------------------------------------------------------

    def overview(self) -> Dict[str, Any]:
        safety = self.db.latest_safety_score() or {}
        run = self.db.current_bot_run() or {}
        health = self.db.latest_symbol_health()
        closed = self.db.closed_paper_trades(limit=5000)
        memory = build_prediction_memory(self.db.outcomes(limit=5000))

        live = self._observer_live(run)
        cycle = self._latest_cycle()
        dd = _drawdown(closed)
        equity = cycle.get("equity", dd["equity"])

        ranked = sorted(health, key=lambda h: h.get("safety_score") or 0,
                        reverse=True)
        return {
            "safety_score": safety.get("score", 50.0),
            "status": safety.get("status", "WAIT"),
            "condition": safety.get("condition", "MIXED"),
            "reasons": _json_field(safety.get("reasons")) or [],
            "bot_running": live,
            "bot_status": run.get("status", "never started"),
            "cycles": run.get("cycles", 0),
            "last_heartbeat": run.get("last_heartbeat_ts"),
            "equity": equity,
            "starting_cash": _STARTING_CASH,
            "drawdown_pct": cycle.get("drawdown_pct", dd["max_drawdown_pct"] / 100.0),
            "max_drawdown_pct": dd["max_drawdown_pct"],
            "symbols_observed": len(health),
            "best_symbols": [self._mini(h) for h in ranked[:3]],
            "worst_symbols": [self._mini(h) for h in reversed(ranked[-3:])]
            if len(ranked) >= 3 else [],
            "model_reliable": memory.is_reliable,
            "prediction_accuracy": round(memory.overall_accuracy * 100, 1),
            "updated": datetime.now(timezone.utc).isoformat(),
        }

    def symbols(self) -> List[Dict[str, Any]]:
        health = {h["symbol"]: h for h in self.db.latest_symbol_health()}
        snaps = {s["symbol"]: s for s in self.db.latest_snapshots()}
        preds = self._latest_prediction_per_symbol()
        rows: List[Dict[str, Any]] = []
        for symbol, h in sorted(health.items()):
            s = snaps.get(symbol, {})
            p = preds.get(symbol, {})
            rows.append({
                "symbol": symbol,
                "price": s.get("price"),
                "trend": _trend_label(s.get("trend_slope")),
                "volatility": s.get("volatility"),
                "liquidity": h.get("book_notional"),
                "spread_bps": s.get("spread_bps"),
                "imbalance": s.get("imbalance"),
                "chop": bool(s.get("chop")),
                "prediction": p.get("direction", "—"),
                "confidence": p.get("confidence"),
                "recent_accuracy": h.get("recent_accuracy"),
                "safety_score": h.get("safety_score"),
                "status": h.get("status", "WATCH ONLY"),
            })
        return rows

    def symbol_detail(self, symbol: str) -> Dict[str, Any]:
        symbol = symbol.upper()
        snaps = self.db.snapshots_for(symbol, limit=240)
        preds = self.db.recent_predictions(limit=60, symbol=symbol)
        health = {h["symbol"]: h for h in self.db.latest_symbol_health()}
        closed = [t for t in self.db.closed_paper_trades(limit=2000)
                  if t["symbol"] == symbol]
        open_trades = [t for t in self.db.open_paper_trades()
                       if t["symbol"] == symbol]
        return {
            "symbol": symbol,
            "health": health.get(symbol, {}),
            "series": [{
                "ts": s["ts"], "price": s["price"], "rsi": s["rsi"],
                "macd": s["macd"], "volatility": s["volatility"],
                "trend_slope": s["trend_slope"], "spread_bps": s["spread_bps"],
                "imbalance": s["imbalance"], "chop": bool(s["chop"]),
            } for s in snaps],
            "predictions": [{
                "ts": p["ts"], "direction": p["direction"],
                "confidence": p["confidence"], "entry": p["entry"],
                "stop": p["stop"], "target": p["target"],
                "condition": p["market_condition"],
            } for p in preds],
            "paper_trades": {"open": open_trades, "closed": closed[:50]},
        }

    def accuracy(self) -> Dict[str, Any]:
        outcomes = self.db.outcomes(limit=5000)
        memory = build_prediction_memory(outcomes)
        return {
            "overall_accuracy": round(memory.overall_accuracy * 100, 1),
            "total_evaluated": memory.total,
            "reliable": memory.is_reliable,
            "should_stop": memory.should_stop_trading(),
            "by_symbol": {k: {"accuracy": round(g.accuracy * 100, 1),
                              "samples": g.samples}
                          for k, g in memory.by_symbol.items()},
            "by_condition": {k: {"accuracy": round(g.accuracy * 100, 1),
                                 "samples": g.samples}
                             for k, g in memory.by_condition.items()},
            "confidence_calibration": {
                k: {"accuracy": round(g.accuracy * 100, 1),
                    "stated_confidence": round(g.mean_confidence * 100, 1),
                    "samples": g.samples}
                for k, g in memory.confidence_buckets.items()},
            "false_confidence_warnings": memory.false_confidence_warnings(),
            "best_regimes": memory.best_regimes(),
            "worst_regimes": memory.worst_regimes(),
        }

    def paper(self) -> Dict[str, Any]:
        closed = self.db.closed_paper_trades(limit=5000)
        open_trades = self.db.open_paper_trades()
        dd = _drawdown(closed)
        wins = [t for t in closed if (t.get("pnl") or 0) > 0]
        best = max(closed, key=lambda t: t.get("pnl") or 0, default=None)
        worst = min(closed, key=lambda t: t.get("pnl") or 0, default=None)
        return {
            "equity": dd["equity"],
            "starting_cash": _STARTING_CASH,
            "total_pnl": round(dd["equity"] - _STARTING_CASH, 2),
            "max_drawdown_pct": dd["max_drawdown_pct"],
            "open_positions": open_trades,
            "closed_trades": closed[:100],
            "closed_count": len(closed),
            "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
            "total_fees": round(sum(t.get("fees") or 0 for t in closed), 2),
            "total_slippage": round(sum(t.get("slippage") or 0 for t in closed), 2),
            "best_trade": best,
            "worst_trade": worst,
        }

    def risk(self) -> Dict[str, Any]:
        health = self.db.latest_symbol_health()
        memory = build_prediction_memory(self.db.outcomes(limit=5000))
        hazardous = [h for h in health
                     if h.get("status") in ("PANIC", "TOO ILLIQUID",
                                             "TOO CHOPPY")]
        return {
            "errors": self.db.recent_errors(limit=40),
            "illiquid_symbols": [h["symbol"] for h in health
                                 if h.get("status") == "TOO ILLIQUID"],
            "panic_symbols": [h["symbol"] for h in health
                              if h.get("status") == "PANIC"],
            "choppy_symbols": [h["symbol"] for h in health
                               if h.get("status") == "TOO CHOPPY"],
            "skipped": [{"symbol": h["symbol"], "status": h["status"],
                         "reasons": _json_field(h.get("rejections")) or []}
                        for h in hazardous],
            "false_confidence_warnings": memory.false_confidence_warnings(),
            "model_unreliable": not memory.is_reliable,
            "should_stop_trading": memory.should_stop_trading(),
        }

    def safety_history(self, limit: int = 200) -> List[Dict[str, Any]]:
        return [{"ts": s["ts"], "score": s["score"], "status": s["status"],
                 "condition": s["condition"]}
                for s in self.db.safety_score_history(limit)]

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _mini(h: Dict[str, Any]) -> Dict[str, Any]:
        return {"symbol": h.get("symbol"), "safety_score": h.get("safety_score"),
                "status": h.get("status")}

    def _latest_prediction_per_symbol(self) -> Dict[str, Dict[str, Any]]:
        preds = self.db.recent_predictions(limit=400)
        out: Dict[str, Dict[str, Any]] = {}
        for p in preds:  # recent_predictions is newest-first
            out.setdefault(p["symbol"], p)
        return out

    def _observer_live(self, run: Dict[str, Any]) -> bool:
        if run.get("status") != "running":
            return False
        hb = run.get("last_heartbeat_ts")
        if not hb:
            return False
        try:
            delta = (datetime.now(timezone.utc)
                     - datetime.fromisoformat(hb)).total_seconds()
        except (ValueError, TypeError):
            return False
        return delta < _HEARTBEAT_STALE_SECONDS

    @staticmethod
    def _latest_cycle() -> Dict[str, Any]:
        if _LATEST_CYCLE.exists():
            try:
                return json.loads(_LATEST_CYCLE.read_text())
            except (ValueError, OSError):
                return {}
        return {}

    def close(self) -> None:
        self.db.close()
