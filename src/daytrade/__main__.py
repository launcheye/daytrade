"""Enable ``python -m daytrade`` as an alias for the ``trading-bot`` CLI."""

from __future__ import annotations

from .cli.main import app

if __name__ == "__main__":
    app()
