"""Market Safety Observatory — continuous paper observation & analysis.

Runs forever, simulates trades, compares predictions to reality, scores how
safe market conditions are, and feeds a dashboard. Observation and paper
simulation only — never real orders.
"""

from __future__ import annotations

from .alerts import Alert, AlertManager, build_condition_alerts
from .daily_report import build_daily_report_markdown, write_daily_report
from .database import DEFAULT_DB_PATH, ObservatoryDB
from .feed import LiveMockFeed, known_symbols, profile_for
from .observer import CycleSummary, Observer
from .prediction_tracker import (
    HORIZONS,
    PredictionMemory,
    build_prediction_memory,
    evaluate_prediction,
)
from .safety_score import (
    SafetyAssessment,
    SafetyInputs,
    aggregate_safety,
    compute_safety_score,
)

__all__ = [
    "ObservatoryDB",
    "DEFAULT_DB_PATH",
    "LiveMockFeed",
    "known_symbols",
    "profile_for",
    "Observer",
    "CycleSummary",
    "SafetyInputs",
    "SafetyAssessment",
    "compute_safety_score",
    "aggregate_safety",
    "evaluate_prediction",
    "build_prediction_memory",
    "PredictionMemory",
    "HORIZONS",
    "Alert",
    "AlertManager",
    "build_condition_alerts",
    "build_daily_report_markdown",
    "write_daily_report",
]
