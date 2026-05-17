# quotex-bot

Modular framework for experimenting with automated trading strategies on
Quotex, on a **demo account**.

## Read this first (honest framing)

- **No official API.** Quotex has none. The live connector will use an
  unofficial reverse-engineered WebSocket lib — fragile, breaks on their
  changes, and against Quotex's ToS (account/fund risk). This is why the
  whole system is built to run and be proven *without* it.
- **The math is against you.** Fixed-time options pay ~85% on a ~50/50
  outcome, so you must win **> 54%** of trades just to break even. A bot
  doesn't fix this — it only finds out faster. "It works" = win rate beats
  that breakeven on *real* data, not "the code runs".
- **Demo by default, enforced in code.** Real money needs *two* explicit
  switches (`config.py`) plus a per-order guard (`executor.py`). One
  misconfig can't route to real funds.

## Setup

```bash
pip install -r requirements.txt        # core deps (Python 3.14 OK)
cp .env.example .env                   # leave QUOTEX_ACCOUNT_MODE=demo
```

## Use it

```bash
# 1. Prove a strategy on data (synthetic by default — expect NO edge)
python scripts/run_backtest.py
python scripts/run_backtest.py --strategy sma_cross --csv data/eurusd.csv

# 2. Paper-trade the full pipeline (simulated connector, no money/network)
python scripts/run_live.py --strategy rsi

# 3. Tests (safety guards + core logic)
python -m pytest -q
```

### Live DEMO trading on Quotex

```bash
cp .env.example .env          # fill QUOTEX_EMAIL / QUOTEX_PASSWORD
                              # leave QUOTEX_ACCOUNT_MODE=demo
python scripts/check_connection.py            # verify + prove demo guard
python scripts/run_live.py --connector quotex --asset EURUSD_otc --strategy rsi
```

`EURUSD_otc` (OTC) trades 24/7 incl. weekends; non-OTC pairs follow market
hours. Stop with Ctrl+C. The risk limits in `.env` apply here too.

## Architecture

`connector/` is the only Quotex-coupled seam — the unofficial pyquotex client
is **vendored** in `vendor/pyquotex` (verified importing on Python 3.14.4) and
wrapped by `src/connector/quotex.py`, which bridges its async API to our sync
code via one background event loop. `strategies/` are pure `candles -> Signal`
functions. `risk.py` enforces stake / daily-loss / trade-count limits + kill
switch. Three independent demo guards: `config.py` (mode), `QuotexConnector`
(live-account re-check every order), `executor.py` (per-order block).

## Troubleshooting

- **`connect failed` / hangs on first run**: Quotex fronts login with
  Cloudflare and may require email 2FA. Re-run; pyquotex caches the session
  after the first success. Persistent failure usually means wrong
  credentials or Cloudflare blocking the IP.
- **`buy rejected` / asset closed**: use an `_otc` asset (e.g.
  `EURUSD_otc`) outside FX market hours.
- **pyquotex breaks after a Quotex update**: only `vendor/pyquotex` +
  `src/connector/quotex.py` are affected; re-vendor a newer pyquotex commit.
