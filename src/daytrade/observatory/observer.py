"""The continuous Market Safety Observer.

Runs forever (until Ctrl+C). Each cycle it, for every healthy watchlist
symbol: fetches data, runs the full analysis pipeline, scores market safety,
records a prediction, steps the paper-trading simulation, and evaluates older
predictions against what actually happened. Everything is written to the
SQLite database and the log file.

It is built to survive: a per-cycle exception is logged and the loop
continues; signals trigger a graceful shutdown; all state lives in the
database, so a restart resumes cleanly (open paper positions are reloaded).

This is observation and paper simulation only — no real orders, ever.
"""

from __future__ import annotations

import json
import os
import signal
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from ..config.schema import AppConfig
from ..models import Action, Side
from ..pipeline import AnalysisPipeline
from ..risk import RiskEngine, position_size
from ..runtime import add_file_logging, get_logger
from ..watchlist import WatchlistScreener, extract_metrics
from .alerts import AlertManager, Alert, LEVEL_CRITICAL, build_condition_alerts
from .database import ObservatoryDB
from .feed import LiveMockFeed
from .prediction_tracker import build_prediction_memory, evaluate_prediction
from .safety_score import SafetyInputs, aggregate_safety, compute_safety_score

_log = get_logger("observatory.observer")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LOG_FILE = _REPO_ROOT / "logs" / "daytrade.log"
_OBSERVER_REPORTS = _REPO_ROOT / "reports" / "observer"


@dataclass
class CycleSummary:
    """A one-line-per-cycle summary of what the observer did."""

    cycle: int
    timestamp: str
    symbols_observed: int = 0
    tradeable: int = 0
    predictions_made: int = 0
    predictions_evaluated: int = 0
    open_trades: int = 0
    closed_this_cycle: int = 0
    global_score: float = 50.0
    global_status: str = "WAIT"
    global_condition: str = "MIXED"
    equity: float = 0.0
    drawdown_pct: float = 0.0
    recent_accuracy: Optional[float] = None
    alerts: List[str] = field(default_factory=list)


class Observer:
    """The continuous observatory engine."""

    def __init__(
        self,
        config: AppConfig,
        watchlist_config,
        db: Optional[ObservatoryDB] = None,
        feed: Optional[LiveMockFeed] = None,
        model=None,
    ) -> None:
        self.config = config
        self.watchlist_config = watchlist_config
        self.db = db or ObservatoryDB()
        self.feed = feed or LiveMockFeed()
        self.pipeline = AnalysisPipeline(config, model)
        self.screener = WatchlistScreener(watchlist_config)
        self.alerts = AlertManager(
            db=self.db, allow_network=config.runtime.allow_network)

        self._run_id: Optional[int] = None
        self._cycle = 0
        self._stop = False
        self._starting_cash = config.paper.starting_cash
        # symbol -> open paper position {trade_id, qty, entry, stop, target}
        self._open: Dict[str, Dict[str, float]] = {}
        self._risk = RiskEngine(config.risk, self._starting_cash)
        self._peak_equity = self._starting_cash

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Begin a run: recover from any prior crash, register this run."""
        add_file_logging(str(_LOG_FILE))
        _OBSERVER_REPORTS.mkdir(parents=True, exist_ok=True)
        crashed = self.db.mark_dangling_runs_crashed()
        if crashed:
            _log.warning("recovered %d crashed/abandoned prior run(s)", crashed)
        self._run_id = self.db.start_bot_run(pid=os.getpid())
        self._reload_open_positions()
        _log.info("observer run #%d started (pid=%d), %d open position(s) reloaded",
                  self._run_id, os.getpid(), len(self._open))

    def stop(self, status: str = "stopped") -> None:
        if self._run_id is not None:
            self.db.stop_bot_run(self._run_id, status)
        _log.info("observer run #%d %s after %d cycle(s)",
                  self._run_id, status, self._cycle)

    def _reload_open_positions(self) -> None:
        """Restart-safety: re-adopt paper positions left open by a prior run."""
        for trade in self.db.open_paper_trades():
            self._open[trade["symbol"]] = {
                "trade_id": trade["id"], "qty": trade["quantity"],
                "entry": trade["entry_price"], "stop": trade["stop"],
                "target": trade["target"],
            }

    # -- the cycle -----------------------------------------------------------

    def run_once(self, now: Optional[datetime] = None) -> CycleSummary:
        """Execute exactly one observation cycle and return its summary."""
        now = now or datetime.now(timezone.utc)
        self._cycle += 1
        summary = CycleSummary(cycle=self._cycle, timestamp=now.isoformat())

        memory = build_prediction_memory(self.db.outcomes(limit=500))
        recent_accuracy = memory.overall_accuracy if memory.total >= 10 else None
        summary.recent_accuracy = recent_accuracy

        equity = self._equity(now)
        self._risk.observe_equity(now, equity)

        assessments = []
        illiquid: List[str] = []
        for symbol in self.watchlist_config.symbols:
            try:
                assessment = self._observe_symbol(symbol, now, memory,
                                                  recent_accuracy, equity)
            except Exception as exc:  # noqa: BLE001 - one symbol must not kill the cycle
                self.db.insert_error(f"observe:{symbol}", repr(exc))
                _log.exception("error observing %s", symbol)
                continue
            summary.symbols_observed += 1
            if assessment is not None:
                assessments.append(assessment)
                summary.tradeable += 1
                if assessment.condition == "ILLIQUID":
                    illiquid.append(symbol)
            summary.predictions_made += 1

        # Evaluate matured predictions against reality.
        summary.predictions_evaluated = self._evaluate_predictions(now)

        # Manage open paper positions (stop / target exits).
        summary.closed_this_cycle = self._manage_positions(now)
        summary.open_trades = len(self._open)

        equity = self._equity(now)
        summary.equity = round(equity, 2)
        self._peak_equity = max(self._peak_equity, equity)
        drawdown = (self._peak_equity - equity) / self._peak_equity \
            if self._peak_equity > 0 else 0.0
        summary.drawdown_pct = round(drawdown, 4)

        # Global safety score.
        global_assessment = aggregate_safety(assessments)
        summary.global_score = global_assessment.score
        summary.global_status = global_assessment.status
        summary.global_condition = global_assessment.condition
        self.db.insert_safety_score(
            ts=now.isoformat(),
            score=global_assessment.score, status=global_assessment.status,
            condition=global_assessment.condition,
            reasons=global_assessment.reasons,
            breakdown=global_assessment.breakdown)

        # Alerts.
        alerts = build_condition_alerts(
            global_condition=global_assessment.condition,
            illiquid_symbols=illiquid, paper_drawdown_pct=drawdown,
            max_drawdown_pct=self.config.risk.max_daily_loss_pct,
            recent_accuracy=recent_accuracy, now=now)
        for alert in alerts:
            if self.alerts.emit(alert):
                summary.alerts.append(f"{alert.kind}: {alert.message}")

        # Heartbeat + per-cycle report artifact.
        if self._run_id is not None:
            self.db.heartbeat(self._run_id, self._cycle)
        self._write_cycle_report(summary)
        _log.info("cycle %d: score=%.0f %s/%s | %d tradeable | equity=%.0f "
                  "dd=%.1f%%", summary.cycle, summary.global_score,
                  summary.global_status, summary.global_condition,
                  summary.tradeable, summary.equity, summary.drawdown_pct * 100)
        return summary

    def _observe_symbol(self, symbol: str, now: datetime, memory,
                        recent_accuracy: Optional[float], equity: float):
        """Observe one symbol: analyse, score, record, maybe paper-trade."""
        candles = self.feed.candles_at(symbol, now, n_bars=240)
        orderbook = self.feed.orderbook_at(symbol, now)
        tick = self.feed.tick_at(symbol, now)
        price = candles[-1].close

        result = self.pipeline.analyze(candles, orderbook, reference_price=price)
        tech, micro, macro = result.technical, result.microstructure, result.macro
        decision = result.decision

        # --- watchlist health screening ---
        metrics = extract_metrics(symbol, tick, orderbook, candles)
        screening = self.screener.screen_one(symbol, tick, orderbook, candles)

        liquidity_notional = (orderbook.notional_depth("bid")
                              + orderbook.notional_depth("ask"))
        panic = (macro.regime_label in ("panic", "war", "exchange_collapse")
                 or result.kill_switch.macro_triggered)
        spread_bps = micro.spread_bps or 0.0
        slippage_bps = self.config.risk.base_slippage_bps + spread_bps * 0.5
        trend_strength = min(1.2, abs(tech.trend_slope or 0.0) / 0.002)
        sym_accuracy = None
        if symbol in memory.by_symbol and memory.by_symbol[symbol].samples >= 5:
            sym_accuracy = memory.by_symbol[symbol].accuracy

        safety = compute_safety_score(SafetyInputs(
            trend_strength=trend_strength,
            volatility=tech.volatility or 0.0,
            liquidity_notional=liquidity_notional,
            spread_bps=spread_bps,
            imbalance=micro.imbalance,
            chop=micro.chop_zone,
            slippage_estimate_bps=slippage_bps,
            panic=panic,
            recent_accuracy=sym_accuracy if sym_accuracy is not None
            else recent_accuracy,
            paper_drawdown_pct=0.0,
            prediction_reliability=recent_accuracy,
        ))

        # --- persist snapshot, prediction, symbol health ---
        # Timestamps use the OBSERVATION time so prediction outcomes can be
        # evaluated against the feed at exactly predicted_ts + horizon.
        ts = now.isoformat()
        self.db.insert_snapshot(
            ts=ts, symbol=symbol, price=price, rsi=tech.rsi, macd=tech.macd,
            volatility=tech.volatility, trend_slope=tech.trend_slope,
            spread_bps=spread_bps, imbalance=micro.imbalance,
            chop=int(micro.chop_zone), liquidity_notional=liquidity_notional,
            regime=micro.regime.value)

        prediction_id = self.db.insert_prediction(
            ts=ts, symbol=symbol, direction=decision.action.value,
            confidence=decision.confidence, entry=decision.entry,
            stop=decision.stop, target=decision.target,
            market_condition=safety.condition, fused_score=decision.fused_score,
            reasons=decision.reasoning)

        status = self._symbol_status(safety, screening, decision)
        self.db.insert_symbol_health(
            ts=ts, symbol=symbol, price=price, volume_24h=metrics.volume_24h_usd,
            spread_bps=spread_bps, book_notional=liquidity_notional,
            healthy=int(screening.approved), rejections=screening.rejections,
            recent_accuracy=sym_accuracy, safety_score=safety.score,
            status=status)

        # --- paper-trading simulation step (entry only; exits in _manage) ---
        self._maybe_open_position(symbol, decision, screening, price,
                                  liquidity_notional, equity, now,
                                  prediction_id)
        return safety

    def _evaluate_predictions(self, now: datetime) -> int:
        """Score every matured-but-unevaluated prediction against reality."""
        evaluated = 0
        for prediction in self.db.unevaluated_predictions():
            outcome, fully = evaluate_prediction(prediction, self.feed, now)
            if outcome is None:
                continue
            self.db.upsert_outcome(prediction["id"], **outcome)
            if fully:
                self.db.mark_prediction_evaluated(prediction["id"])
            evaluated += 1
        return evaluated

    # -- paper trading -------------------------------------------------------

    def _maybe_open_position(self, symbol: str, decision, screening, price: float,
                             liquidity_notional: float, equity: float,
                             now: datetime, prediction_id: int) -> None:
        if symbol in self._open or not screening.approved:
            return
        if decision.action is not Action.BUY or decision.kill_switch_active:
            return
        if not (decision.entry and decision.stop and decision.target):
            return
        permission = self._risk.evaluate_entry(
            equity, open_positions=len(self._open), bar_index=self._cycle)
        if not permission.allowed:
            return
        sizing = position_size(equity, decision.entry, decision.stop,
                               self.config.risk)
        if not sizing.is_tradeable:
            return
        trade_id = self.db.insert_paper_trade(
            symbol=symbol, side=Side.BUY.value, quantity=sizing.quantity,
            entry_price=decision.entry, stop=decision.stop,
            target=decision.target, fees=0.0, slippage=0.0, pnl=0.0)
        self._open[symbol] = {
            "trade_id": trade_id, "qty": sizing.quantity,
            "entry": decision.entry, "stop": decision.stop,
            "target": decision.target,
        }
        _log.info("paper-opened %s qty=%.6f entry=%.4f (sim)",
                  symbol, sizing.quantity, decision.entry)

    def _manage_positions(self, now: datetime) -> int:
        """Close any open paper position whose stop or target was reached."""
        closed = 0
        for symbol, pos in list(self._open.items()):
            price = self.feed.price_at(symbol, now)
            exit_price: Optional[float] = None
            if price <= pos["stop"]:
                exit_price = pos["stop"]
            elif price >= pos["target"]:
                exit_price = pos["target"]
            if exit_price is None:
                continue
            qty = pos["qty"]
            gross = (exit_price - pos["entry"]) * qty
            fee = (exit_price + pos["entry"]) * qty * \
                self.config.risk.fee_bps / 10_000.0
            pnl = gross - fee
            slippage = exit_price * 0.0004 * qty
            self.db.close_paper_trade(pos["trade_id"], exit_price=exit_price,
                                      pnl=pnl, fees=fee, slippage=slippage)
            self._risk.register_trade_close(pnl, self._cycle)
            del self._open[symbol]
            closed += 1
            _log.info("paper-closed %s exit=%.4f pnl=%.2f (sim)",
                      symbol, exit_price, pnl)
        return closed

    def _equity(self, now: datetime) -> float:
        """Simulated equity = cash + realised PnL + open unrealised PnL."""
        realized = sum(t["pnl"] or 0.0 for t in self.db.closed_paper_trades())
        unrealized = 0.0
        for symbol, pos in self._open.items():
            price = self.feed.price_at(symbol, now)
            unrealized += (price - pos["entry"]) * pos["qty"]
        return self._starting_cash + realized + unrealized

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _symbol_status(safety, screening, decision) -> str:
        """Map a symbol's state to a dashboard status label."""
        if not screening.approved:
            if any("liquidity" in r or "orderbook" in r
                   for r in screening.rejections):
                return "TOO ILLIQUID"
            return "WATCH ONLY"
        if safety.condition == "PANIC":
            return "PANIC"
        if safety.condition == "ILLIQUID":
            return "TOO ILLIQUID"
        if safety.condition == "CHOPPY":
            return "TOO CHOPPY"
        if decision.kill_switch_active:
            return "WATCH ONLY"
        if safety.score >= 65:
            return "GOOD PAPER CONDITIONS"
        return "WATCH ONLY"

    def _write_cycle_report(self, summary: CycleSummary) -> None:
        """Write the cycle summary to reports/observer/ (latest + run log)."""
        try:
            (_OBSERVER_REPORTS / "latest.json").write_text(
                json.dumps(asdict(summary), indent=2))
            run_log = _OBSERVER_REPORTS / f"run_{self._run_id}.jsonl"
            with run_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(summary)) + "\n")
        except OSError as exc:  # pragma: no cover - disk issues must not crash
            _log.warning("could not write cycle report: %s", exc)

    # -- the forever loop ----------------------------------------------------

    def run_forever(self, interval: int = 300) -> None:
        """Run cycles every ``interval`` seconds until interrupted."""
        self._install_signal_handlers()
        self.start()
        consecutive_failures = 0
        try:
            while not self._stop:
                try:
                    self.run_once()
                    consecutive_failures = 0
                except Exception as exc:  # noqa: BLE001 - crash recovery
                    consecutive_failures += 1
                    self.db.insert_error("cycle", repr(exc))
                    _log.exception("cycle failed (%d in a row)",
                                   consecutive_failures)
                    self.alerts.emit(Alert(
                        LEVEL_CRITICAL, "crash",
                        f"observer cycle crashed: {exc!r}",
                        datetime.now(timezone.utc)))
                # Sleep in short slices so Ctrl+C is responsive.
                slept = 0.0
                while slept < interval and not self._stop:
                    time.sleep(min(1.0, interval - slept))
                    slept += 1.0
        finally:
            self.stop("stopped" if self._stop else "crashed")
            self.db.close()

    def _install_signal_handlers(self) -> None:
        def _handler(signum, _frame):
            _log.info("signal %d received — shutting down gracefully", signum)
            self._stop = True
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handler)
            except ValueError:  # pragma: no cover - not on main thread (tests)
                pass
