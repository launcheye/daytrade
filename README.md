# daytrade

**Multi-layer educational trading research & paper-trading platform.**

> ⚠️ **EDUCATIONAL ONLY. THIS SOFTWARE CANNOT PLACE REAL TRADES.**
> Every execution path is simulated. Any function that would touch a live
> broker raises `NotImplementedError("Real trading is disabled.")`.
> No leverage, no futures, no margin, no withdrawal credentials — by design.

> ⚠️ **Backtests are NOT reality.** Historical simulation systematically
> overstates performance. This platform deliberately models spread, slippage,
> latency, partial fills, fees and regime shifts to *narrow* — never close —
> that gap.

---

## What this is

A research-grade reference implementation of an intelligent trading pipeline,
built for learning how the pieces of a quant stack fit together:

```
market data ─▶ consensus ─▶ indicators ─┐
                                         ├─▶ feature pipeline ─▶ ML model ─┐
orderbook ──▶ microstructure analysis ───┤                                 │
macro context (mock / Gemini) ───────────┘                                 │
                                                                            ▼
                          kill switches ◀─── AI fusion engine ◀─────────────┘
                                │
                                ▼
                  risk engine ─▶ paper broker ─▶ reporting
```

## Install

```bash
python -m pip install -e ".[dev]"
```

## Quick start

```bash
trading-bot demo          # run the canonical BTC decision demo
trading-bot paper         # run a paper-trading session on mock data
trading-bot backtest      # run a backtest with realistic execution
trading-bot train         # train the ML model with walk-forward validation
trading-bot simulate      # full end-to-end simulation + report
trading-bot config        # show the active (validated) configuration

# operations layer
trading-bot watchlist     # screen the multi-asset watchlist for liquidity
trading-bot approve       # decide a trade and require manual CLI approval
trading-bot accounting    # accounting report (+ optional tax CSV export)
trading-bot daily-report  # end-of-session operations report
trading-bot sandbox-check # verify sandbox setup; prove real execution off

# 24/7 Market Safety Observatory
trading-bot observe --interval 300   # run the continuous observer (Ctrl+C to stop)
trading-bot dashboard                # launch the visual dashboard (FastAPI + web UI)
trading-bot status                   # show observatory status
trading-bot report-daily             # generate today's daily report
trading-bot watchlist-check          # screen configs/watchlist.yaml

# 30-Day Paper Trading Learning Observatory
trading-bot learn --days 30 --interval 300   # run the 30-day learning observatory

# Historical research lab
trading-bot research --symbol BTCUSDT --interval 1h --days 365   # backtest over real history
```

`make learn`, `make research`, `make observe`, `make dashboard`, `make report`,
`make status` and `make test` are also provided.

## Historical research lab

`trading-bot research` downloads **real Binance history** (read-only public
data, cached locally) and runs the same backtest + walk-forward engines the
live observatory uses — collapsing a 30-day experiment into minutes. It is
deliberately ruthless: its job is to tell you a strategy has *no edge*,
quickly and on real data, so the rare one that does is worth a live 30-day
confirmation. Research only — no orders.

By default everything runs **offline** against a deterministic mock exchange.
Set `DAYTRADE_ALLOW_NETWORK=true` to allow read-only public market-data calls.

## Paper / sandbox operations

The platform monitors many crypto pairs but **only paper-trades or
sandbox-trades** — it never places real orders or moves money.

- **Watchlist** — assets are screened for 24h volume, spread, orderbook
  depth and pump-and-dump movement before they are tradeable.
- **Manual approval** — every trade prints a full card (entry/stop/target,
  confidence, risk, expected slippage, liquidity & kill-switch status) and
  requires the operator to type the confirmation phrase.
- **Sandbox (testnet)** — opt-in, off by default. Execution is locked to an
  exchange-testnet URL allowlist; API keys are loaded from `.env`, must be
  read-only by default, and **any key with withdrawal permission is
  rejected on connect**. There is no mainnet execution path.
- **Risk controls** — per-coin position cap, daily & weekly loss limits,
  max open positions, post-loss cooldown, plus spread/liquidity/chop and
  confidence gates.

## Market Safety Observatory

`trading-bot observe` runs **forever** (until Ctrl+C). Each cycle it fetches
data, runs every analysis (technical, microstructure, volatility, trend,
chop, liquidity, regime/panic), paper-simulates trades, stores every
prediction, and later compares predictions to what actually happened. It is
crash-recovering and restart-safe — all state lives in a SQLite database
(`artifacts/observatory.db`); logs go to `logs/daytrade.log`.

`trading-bot dashboard` opens a visual dashboard (default
`http://127.0.0.1:8000`) with a giant **MARKET STATUS** card, a
safety-score timeline, a per-symbol table, prediction-accuracy analytics, a
paper-trading view and a risk console — live via WebSocket.

The **Market Safety Score** (0-100) summarizes conditions as
`SAFE_TO_OBSERVE` / `WAIT` / `HIGH_RISK` / `UNSAFE`, with a market condition
of `CALM` / `OPPORTUNISTIC` / `MIXED` / `CHOPPY` / `PANIC` / `ILLIQUID` /
`OVEREXTENDED`. It describes *observation conditions for this paper
strategy* — never investment advice.

It is a market **training simulator and safety dashboard**: it monitors many
pairs, learns which regimes it predicts well, flags when its confidence is
"fake", and only ever paper-trades.

## 30-Day Paper Trading Learning Observatory

`trading-bot learn --days 30` runs the observatory as a **multi-day learning
session**. It is restart-safe — the 30-day clock is persisted to
`data/learning_state.json` and resumes where it left off.

The dashboard then shows, at a glance:

- **Progress** — day N/30, learning progress %, cycles completed vs expected,
  uptime, and the current learning phase (Warm-up → Data collection → Pattern
  discovery → Reliability testing → Stress testing → Final evaluation).
- **Day timeline** — one cell per day, green/yellow/red by how well it ran.
- **Paper Strategy Readiness** — a 0-100 score (NOT ENOUGH DATA → UNRELIABLE →
  PROMISING BUT UNPROVEN → STABLE IN PAPER CONDITIONS → STRONG PAPER
  PERFORMANCE, STILL NOT GUARANTEED). **Capped at 60 before day 30** so the
  dashboard cannot turn falsely optimistic early.
- **Regime dashboard** — accuracy and fake PnL per market regime, so you can
  see which regimes the strategy works in and which destroy it.
- **Confidence calibration** — does an 80%-confidence prediction actually win
  ~80% of the time? Overconfidence is flagged.
- **Live activity feed** + a **"what is it doing right now"** panel (current
  cycle, current step, current symbol, next cycle).

The readiness score and reports never say "safe to invest" — only whether
*paper conditions look stable* or the *strategy is currently unreliable*.

## Project layout

| Path | Purpose |
|------|---------|
| `src/daytrade/models` | Pydantic domain models |
| `src/daytrade/config` | YAML config loading + validation + env overrides |
| `src/daytrade/exchanges` | Mock + public read-only exchange clients, consensus engine |
| `src/daytrade/indicators` | Vectorized technical indicators (no lookahead) |
| `src/daytrade/microstructure` | Orderbook / liquidity analysis |
| `src/daytrade/features` | Shared online+offline feature pipeline |
| `src/daytrade/labels` | Offline-only label generation |
| `src/daytrade/ml` | Model training / inference |
| `src/daytrade/validation` | Walk-forward validation + leakage checks |
| `src/daytrade/macro` | Macro context engine (mock / Gemini) |
| `src/daytrade/fusion` | AI decision-fusion engine |
| `src/daytrade/safety` | Real-trading guard + macro/micro kill switches |
| `src/daytrade/risk` | Slippage, fees, sizing, daily/weekly loss, cooldown |
| `src/daytrade/watchlist` | Multi-asset liquidity / pump-and-dump screening |
| `src/daytrade/paper` | Paper broker + sandbox broker + portfolio + PnL |
| `src/daytrade/accounting` | Accounting report + tax-CSV export (no transfers) |
| `src/daytrade/backtest` | Backtesting / simulation engine |
| `src/daytrade/reporting` | Console / JSON / Markdown + daily reports |
| `src/daytrade/observatory` | 24/7 observer, SQLite store, safety score, alerts |
| `src/daytrade/dashboard` | FastAPI backend + single-page visual dashboard |
| `src/daytrade/cli` | `trading-bot` command line interface |
| `daytrade/exchanges/sandbox.py` | Testnet-only execution (URL-allowlisted) |
| `daytrade/exchanges/credentials.py` | API-key loading + withdrawal-key rejection |

## Safety model

See [`docs/SAFETY.md`](docs/SAFETY.md). In short: the only broker in this
codebase is `PaperBroker`. There is no code path — and no config flag — that
sends an order to a real exchange.

## Testing

```bash
pytest                       # full suite
pytest -m safety             # "real trading is impossible" tests
pytest -m leakage            # "no lookahead bias" tests
```

## License

MIT — for educational use.
