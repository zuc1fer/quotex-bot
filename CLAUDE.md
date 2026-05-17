# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A modular framework for automated fixed-time-options trading on Quotex,
**demo-account by default**. The economics are adversarial: ~85% payout on a
~50/50 outcome means a strategy must win **> ~54%** (`1/(1+payout)`) just to
break even. "It works" means *win rate beats breakeven on real data*, not "the
code runs". Keep this framing when evaluating changes — a green backtest on
synthetic data proves nothing (synthetic data is a random walk by design; see
`synthetic_series` docstring).

## Commands

```bash
pip install -r requirements.txt          # Python 3.14 OK
python -m pytest -q                       # all tests
python -m pytest tests/test_safety.py -q  # the safety guards (most important)
python -m pytest tests/test_core.py::test_breakeven_math -q   # single test

python scripts/run_backtest.py                                    # all strategies, synthetic
python scripts/run_backtest.py --strategy sma_cross --csv data/eurusd.csv
python scripts/run_live.py --strategy rsi                          # paper-trade, sim connector
python scripts/check_connection.py                                # verify Quotex + demo guard, no trades
python scripts/run_live.py --connector quotex --asset EURUSD_otc --strategy rsi   # live DEMO
```

There is no lint/format config in the repo. Scripts prepend the repo root to
`sys.path` themselves, so run them from anywhere with `python scripts/...`.

## Architecture

The system is deliberately decoupled from Quotex so it stays testable and
provable without the fragile broker integration:

- **`src/connector/base.py` is the only seam coupled to Quotex.** Everything
  else (strategies, risk, backtest, executor) depends on this ABC, never on the
  broker library. Two impls: `SimulatedConnector` (offline, `is_demo` hard-coded
  `True`, cursor-based — call `step()` to advance one candle) and
  `QuotexConnector` (real, unofficial WebSocket).
- **`QuotexConnector` bridges async→sync.** The vendored pyquotex client is
  fully async; the rest of the codebase is sync. One asyncio loop runs in a
  daemon thread (`_LoopThread`); coroutines are marshalled onto it. `buy()`
  spawns `check_win` as a future so `result()` is non-blocking and returns
  `None` until expiry.
- **pyquotex is vendored in `vendor/pyquotex`** (its packaging is broken and
  pins `<4.0` Python). `src/connector/quotex.py` inserts `vendor/` into
  `sys.path` at import. If Quotex changes their protocol, *only*
  `vendor/pyquotex` + `quotex.py` break — re-vendor a newer pyquotex commit; do
  not spread broker logic elsewhere.
- **Strategies are pure `pd.DataFrame -> Signal` functions** (`strategies/base.py`).
  No I/O, no state, no look-ahead (only use rows up to and including the last).
  Register new ones in `src/strategies/__init__.py:REGISTRY` to expose them to
  the CLI scripts. Honor `Strategy.warmup`.
- **`backtest.py` walks bar-by-bar with no look-ahead**: decide on `[0..i]`,
  settle against `close[i + expiry_bars]`. `BacktestResult.has_edge` is the
  verdict that matters.
- **`risk.py` applies in BOTH demo and real** (habits built on demo run on real
  money later): per-trade stake cap, max trades/day, daily-loss kill switch
  (latches until `reset_day()`).

## Real-money safety model (do not weaken)

Real-money trading is gated behind **three independent guards**. Treat any
change touching them as security-sensitive; `tests/test_safety.py` is the most
important test file.

1. **`config.py`** — needs both `QUOTEX_ACCOUNT_MODE=real` *and*
   `QUOTEX_ALLOW_REAL=I_UNDERSTAND_REAL_MONEY_RISK` (exact token). Mismatch
   raises `UnsafeRealModeError` rather than silently falling back.
2. **`QuotexConnector`** — forces the PRACTICE account before *and* after
   connect; `is_demo` reflects the *live session's* account
   (`client.account_is_demo`), never config. Re-checks on **every** `buy()`,
   not just connect.
3. **`Executor._assert_safe()`** — refuses each order if the connector is on a
   real account without explicit opt-in (`RealMoneyBlocked`).

`config.py` calls `load_dotenv()` and reads env at import time, so the safety
tests `importlib.reload(config)` after `monkeypatch`-ing env vars — keep config
re-import-safe (no import-time side effects beyond env reads).

## Conventions

- Domain types live in `src/types.py` and have **no external deps** so every
  module can import them. `Signal` (CALL/PUT/NONE), `Candle`, `TradeResult`.
- Candle DataFrames are `ts, open, high, low, close, volume`, oldest first,
  last row = latest *closed* candle.
- All trades/signals log through `src/logger.py:get_logger(name)` for audit.
- `EURUSD_otc` (OTC) trades 24/7; non-OTC pairs follow FX market hours — a
  closed asset surfaces as `buy rejected`.
