# Strategy improvement plan — fixing the "no edge" problem

Goal: turn the daytrade observatory from a 50%-accuracy, steadily-bleeding
paper strategy into one with a measurable, walk-forward-proven edge — using
techniques that the algorithmic-trading community and academic literature
actually use. Still strictly paper / simulation: no real trading, no wallets,
no money. ML and predictive modelling are used; nothing places a live order.

## The diagnosis (from the live run, 650 evaluated predictions)

| # | Problem | Evidence |
|---|---------|----------|
| 1 | No predictive edge | 50.0% accuracy overall — a coin flip |
| 2 | Trades its weakest regime | 564/650 predictions in CALM, where it is 48% |
| 3 | Overconfident | Says ~65%, delivers ~53%; system flags "fake confidence" |
| 4 | Stops too tight | 50% direction-right but only 15% winning trades — noise stops it out |

## What the research says (sources at the bottom)

- **Win rate vs R:R / expectancy** — profitability is `expectancy`, not win
  rate. With a coin-flip signal you cannot win on win rate; you must win on
  the *quality of the trades you choose to take* and a sound R:R.
- **ATR-based stops** — a fixed stop is too tight in calm markets and gets
  hit by routine noise. Tie the stop to volatility (ATR); day-trading
  multiples are 1.5–3×. Wider stop ⇒ smaller position to keep € risk fixed.
- **Regime filtering** — HMM / Random-Forest regime detectors are used as a
  *gate*: disallow trades in regimes that historically lose. Increases Sharpe
  by removing unprofitable trades rather than adding winners.
- **Probability calibration** — overconfident classifiers are corrected with
  isotonic regression or Platt scaling (`sklearn.calibration`). Maps stated
  probability → empirically-true probability.
- **Meta-labelling (de Prado)** — the highest-leverage idea. Keep the primary
  signal; add a *secondary* ML model whose only job is to answer "should I
  act on this signal?" Trained on triple-barrier outcomes. Studies show large
  precision gains (e.g. precision 0.21 → 0.39). This is the canonical fix for
  "direction is ~right but my trades still lose."
- **Purged walk-forward validation** — standard k-fold leaks future info on
  time series. Every change must be proven with walk-forward / purged CV,
  out-of-sample. Crypto regimes shift fast: use ~90-day windows.

## The plan — 5 phases (~3 hours)

Every phase is proven in the backtest/research lab *before* it touches the
live observatory. Order is deliberate: cheap mechanical fixes first, the
ML-heavy meta-labelling last.

### Phase 0 — Measurement harness (~15 min)
- Make the research lab the proving ground: a repeatable command that runs
  backtest + purged walk-forward on the 35 symbols and prints expectancy,
  win rate, Sharpe, and the overfit gap.
- Record today's numbers as the baseline to beat.

### Phase 1 — Fix the stops · Problem 4 (~30 min)
- The vol unit `U` is already ATR-based. Widen `stop_vol_mult` 1.0 → ~2.0–2.5
  so the stop sits outside routine noise; re-tune `target_vol_mult` for a
  sane ~2:1–2.5:1 R:R; add the triple-barrier "vertical" time-stop.
- Confirm the position sizer shrinks size as the stop widens (constant € risk).
- Sweep the multiple in the backtest; keep the best out-of-sample value.

### Phase 2 — Regime gate · Problem 2 (~30 min)
- Add a gate driven by the bot's *own* rolling accuracy-by-regime: only allow
  trades in regimes whose measured accuracy clears the break-even win rate
  implied by the current R:R. CALM gets blocked until it proves itself;
  MIXED stays open.
- Config-driven `min_regime_accuracy`; self-adjusts as evidence accumulates.

### Phase 3 — Confidence calibration · Problem 3 (~30 min)
- Fit an isotonic / Platt calibration map from the bot's own outcome history
  (stated confidence → actual accuracy).
- Gate trades on the *calibrated* probability, not the raw one. Kills the
  "fake confidence" warnings; surfaces calibrated vs raw on the dashboard.

### Phase 4 — Meta-labelling · Problem 1 (~45 min) — the big lever
- Add triple-barrier labels (did price hit target / stop / time-out first).
- Train a secondary classifier (reuse `ml/model.py`: gradient boosting) that
  predicts P(this trade hits target before stop) from the primary signal +
  microstructure/technical features.
- Live: primary proposes direction → meta-model scores it → trade only if
  P(win) > threshold. Fewer trades, higher precision.
- Prove the precision lift in walk-forward before going live.

### Phase 5 — Wire into live + dashboard (~30 min)
- Integrate Phases 1–4 into the observer decision path.
- Dashboard: regime-gate status, calibrated-vs-raw confidence, meta-model
  filter rate / acceptance rate.
- Restart the 30-day learning run on the improved strategy.

## Definition of done

- Walk-forward expectancy positive (or honestly reported as still negative).
- Calibration gap < 5 points.
- No trades in regimes below break-even accuracy.
- Trade win rate and direction accuracy converge (stops no longer noise-cut).
- Every change covered by tests; full suite green.

## Reference repositories / techniques (studied, not copied)

- `freqtrade/freqtrade` (FreqAI) — adaptive per-regime ML retraining
- `edtechre/pybroker` — ML-first backtesting patterns
- de Prado, *Advances in Financial Machine Learning* — triple-barrier,
  meta-labelling, purged walk-forward CV
- `stefan-jansen/machine-learning-for-trading` — feature engineering
- `scikit-learn` — `CalibratedClassifierCV` (isotonic / sigmoid)

## Sources

- https://algotest.in/blog/understanding-strategy-win-rates-what-does-50-really-mean/
- https://www.luxalgo.com/blog/win-rate-and-riskreward-connection-explained/
- https://www.mql5.com/en/blogs/post/769457 (fixed vs ATR stops)
- https://www.alphaexcapital.com/stocks/technical-analysis-for-stock-trading/trading-strategies-using-technical-analysis/atr-based-stop-loss
- https://blog.quantinsti.com/epat-project-machine-learning-market-regime-detection-random-forest-python/
- https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/
- https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/
- https://www.newsletter.quantreo.com/p/the-triple-barrier-labeling-of-marco
- https://scikit-learn.org/stable/modules/calibration.html
- https://blog.quantinsti.com/walk-forward-optimization-python-xgboost-stock-prediction/
- https://github.com/freqtrade/freqtrade
- https://github.com/edtechre/pybroker
