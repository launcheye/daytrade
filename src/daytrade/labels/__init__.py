"""Label generation — OFFLINE TRAINING ONLY (labels reference future bars)."""

from __future__ import annotations

from .generate import (
    breakout_label,
    directional_label,
    future_return,
    make_labels,
    triple_barrier_label,
)

__all__ = [
    "future_return",
    "directional_label",
    "breakout_label",
    "triple_barrier_label",
    "make_labels",
]
