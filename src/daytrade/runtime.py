"""Cross-cutting runtime helpers: logging and deterministic seeding."""

from __future__ import annotations

import logging
import os
import random
from typing import Optional

import numpy as np

from rich.logging import RichHandler

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging with a Rich handler (idempotent)."""
    global _CONFIGURED
    numeric = getattr(logging, level.upper(), logging.INFO)
    handler = RichHandler(rich_tracebacks=True, show_path=False, markup=False)
    if _CONFIGURED:
        logging.getLogger().setLevel(numeric)
        return
    logging.basicConfig(
        level=numeric,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the ``daytrade`` root."""
    return logging.getLogger(f"daytrade.{name}")


def seed_everything(seed: int = 42) -> None:
    """Seed Python and NumPy RNGs for deterministic, reproducible runs.

    Determinism is a first-class requirement here: a research result you
    cannot reproduce is not a research result.
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)


def apply_runtime(level: str = "INFO", deterministic: bool = True,
                   seed: int = 42) -> None:
    """One-shot runtime setup used by the CLI before any work begins."""
    setup_logging(level)
    if deterministic:
        seed_everything(seed)
