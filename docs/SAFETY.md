# Safety model

`daytrade` is an **educational research platform**. It is structurally
incapable of placing a real trade. This document explains how that guarantee
is enforced — not merely promised.

## 1. There is exactly one broker

The only object that executes orders is `daytrade.paper.PaperBroker`. It
matches orders against simulated liquidity and updates an in-memory portfolio.
No socket is ever opened to an exchange order-entry endpoint.

## 2. The real-trading path raises

`daytrade.safety.guard` exposes `forbid_real_trading()`. Any function that
*would* represent a live-execution boundary calls it, which raises:

```python
NotImplementedError("Real trading is disabled.")
```

There is no argument, config flag, or environment variable that suppresses it.

## 3. Config validation refuses unsafe values

`config.SafetyConfig` validates that:

- `live_trading_enabled` is `false`
- `allow_real_orders` is `false`
- `paper_trading` is `true`

Any other combination makes config loading **fail**. The flags exist so the
safe values are explicit and test-asserted — not so they can be changed.

## 4. No credentials, no leverage

- Exchange clients use **public, read-only** market-data endpoints only.
- No API keys, secrets, or withdrawal credentials are read or stored.
- There is no margin, leverage, futures, or short-selling code path.
- Network access is **off by default** (`runtime.allow_network: false`); with
  it on, only public read-only data endpoints are reachable.

## 5. Tests enforce all of the above

`pytest -m safety` runs the safety suite: it asserts `forbid_real_trading()`
raises, that unsafe configs are rejected, and that no module exposes a
live-order function.

## Why this matters

Backtests and paper trading systematically *overstate* performance. Making
real execution impossible removes the temptation to act on results that have
not survived contact with real markets — slippage, latency, competition, and
the simple fact that the future is not the past.
