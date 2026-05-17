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
```

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
