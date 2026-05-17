# quotex-bot

Modular framework for testing automated trading strategies on Quotex, live on
a **demo account**.

## Read this first (honest framing)

- **No official API.** Quotex has none. The connector uses an unofficial
  reverse-engineered WebSocket lib — fragile, breaks on their changes, and
  against Quotex's ToS (account risk). This is the only way in.
- **The math is against you.** Fixed-time options pay ~85% on a ~50/50
  outcome, so a strategy must win **> 54%** of trades just to break even. A
  bot doesn't fix this — it only finds out faster. There is no backtest here:
  "it works" means the win rate it accumulates *live on demo* beats that
  breakeven, and you need **~100+ trades** before that number means anything.
- **Demo by default, enforced in code.** Real money needs *two* explicit
  switches (`config.py`) plus a per-order guard (`executor.py`) plus the
  connector forcing the PRACTICE account. One misconfig can't route to real
  funds.

## Setup

```bash
pip install -r requirements.txt        # core deps (Python 3.14 OK)
cp .env.example .env                   # fill QUOTEX_EMAIL / QUOTEX_PASSWORD
                                       # leave QUOTEX_ACCOUNT_MODE=demo
```

## Use it

```bash
# 1. Verify the connection + prove the demo guard (places NO trades)
python scripts/check_connection.py

# 2. Trade live on the DEMO account, multi-asset
python scripts/run_live.py --strategy revert --min-payout 0.80

# 3. Tests (safety guards + core logic)
python -m pytest -q
```

`run_live.py` trades every OPEN asset whose short-trade (turbo) payout is
`>= --min-payout`, refreshing that watchlist periodically and firing orders
best-effort concurrently (5s TIMER options). Stop with Ctrl+C. Risk limits in
`.env` (stake / daily-loss / trades-per-day) apply; the kill switch latches if
the daily loss is hit.

Results are resolved from the **authoritative Quotex closed-deal profit**
(`api.listinfodata`), not reconstructed. The vendored client correlates orders
via shared state, so rapid-fire placements can return a duplicate id; those
are detected, dropped, and logged as known noise — never miscounted. The HTTP
trade-history endpoint the vendored lib targets is dead (404 — Quotex moved
it); the websocket closed-deal feed is the same data the UI list shows.

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
