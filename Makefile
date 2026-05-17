# daytrade — Market Safety Observatory
# Paper / simulation only. No real trading, wallets, or money movement.

PY ?= python3

.PHONY: help install learn research observe dashboard report status watchlist test demo backtest clean

help:
	@echo "daytrade — make targets"
	@echo "  make install     install the package (editable, with dev extras)"
	@echo "  make learn       run the 30-day Paper Trading Learning Observatory"
	@echo "  make research    historical research lab — backtest over real history"
	@echo "  make observe     run the 24/7 Market Safety Observer (Ctrl+C to stop)"
	@echo "  make dashboard   launch the visual dashboard at http://127.0.0.1:8000"
	@echo "  make report      generate today's daily observatory report"
	@echo "  make status      show observatory status"
	@echo "  make watchlist   screen the watchlist for liquidity / quality"
	@echo "  make test        run the full test suite"
	@echo "  make demo        run the canonical decision demo"
	@echo "  make backtest    run a backtest"

install:
	$(PY) -m pip install -e ".[dev]"

learn:
	$(PY) -m daytrade learn --days 30 --interval 300

research:
	$(PY) -m daytrade research --symbol BTCUSDT --interval 1h --days 365

observe:
	$(PY) -m daytrade observe --interval 300

dashboard:
	$(PY) -m daytrade dashboard

report:
	$(PY) -m daytrade report-daily

status:
	$(PY) -m daytrade status

watchlist:
	$(PY) -m daytrade watchlist-check

test:
	$(PY) -m pytest -q

demo:
	$(PY) -m daytrade demo

backtest:
	$(PY) -m daytrade backtest

clean:
	rm -rf .pytest_cache __pycache__ src/**/__pycache__ build dist *.egg-info
