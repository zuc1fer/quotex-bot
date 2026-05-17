# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A modular framework for automated fixed-time-options trading on Quotex,
**demo-account only**. There is no backtest and no simulated feed: the project
connects to the real Quotex WebSocket (vendored pyquotex) and trades the
PRACTICE account. The economics are adversarial: ~85% payout on a ~50/50
outcome means a strategy must win **> ~54%** (`1/(1+payout)`) just to break
even. A strategy is judged solely by the win rate it accumulates **live on
demo**, and ~100+ trades are needed before that number is meaningful. Keep
this framing when evaluating changes — "the code runs" is not "it works".

## Commands

```bash
pip install -r requirements.txt          # Python 3.14 OK
python -m pytest -q                       # all tests
python -m pytest tests/test_safety.py -q  # the safety guards (most important)
python -m pytest tests/test_core.py::test_risk_caps_trades_per_day -q   # single test

python scripts/check_connection.py        # verify Quotex login + demo guard, places NO trades
python scripts/run_live.py --asset EURUSD_otc --strategy rsi   # trade live on DEMO
```

Running anything that touches Quotex requires `QUOTEX_EMAIL` / `QUOTEX_PASSWORD`
in `.env` (copy `.env.example`); first login may need a Cloudflare/2FA step.
There is no lint/format config in the repo. Scripts prepend the repo root to
`sys.path` themselves, so run them from anywhere with `python scripts/...`.

## Architecture

The system is deliberately decoupled from Quotex so strategy/risk logic stays
unit-testable without the broker:

- **`src/connector/base.py` is the only seam coupled to Quotex.** Everything
  else (strategies, risk, executor) depends on this ABC, never on the broker
  library. The single concrete impl is `QuotexConnector`.
- **`QuotexConnector` bridges async→sync.** The vendored pyquotex client is
  fully async; the rest of the codebase is sync. One asyncio loop runs in a
  daemon thread (`_LoopThread`); coroutines are marshalled onto it. `buy()`
  spawns `check_win` as a future so `result()` is non-blocking and returns
  `None` until expiry. `run_live.py:run_realtime` polls pending results and
  acts once per freshly-closed candle.
- **pyquotex is vendored in `vendor/pyquotex`** (its packaging is broken and
  pins `<4.0` Python). `src/connector/quotex.py` inserts `vendor/` into
  `sys.path` at import. If Quotex changes their protocol, *only*
  `vendor/pyquotex` + `quotex.py` break — re-vendor a newer pyquotex commit;
  do not spread broker logic elsewhere.
- **Strategies are pure `pd.DataFrame -> Signal` functions** (`strategies/base.py`).
  No I/O, no state, no look-ahead (only use rows up to and including the last).
  Register new ones in `src/strategies/__init__.py:REGISTRY` to expose them to
  `run_live.py --strategy`. Honor `Strategy.warmup`.
- **`risk.py` is the safety net**: per-trade stake cap, max trades/day,
  daily-loss kill switch (latches until `reset_day()`). It is the only thing
  bounding losses since there is no pre-trade proof of edge.

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

`run_live.py` additionally `SystemExit`s if the connected account is not demo.
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
