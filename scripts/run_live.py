"""Live loop on Quotex — DEMO account only, MULTI-ASSET.

Trades every OPEN asset whose short-trade (turbo) payout is >= --min-payout,
refreshing that watchlist periodically. Best-effort concurrent: orders are
fired across assets with minimal spacing. The vendored client correlates
orders via shared state, so rapid-fire placements can collide on order id;
those are detected, dropped, and logged as KNOWN noise (never counted in the
win/loss tally). Results are resolved from the AUTHORITATIVE Quotex
closed-deal profit, not reconstructed.

Demo-gated end to end: config.py refuses unsafe real mode, QuotexConnector
forces PRACTICE and re-checks the live account on every order, executor.py
blocks real orders without explicit opt-in.

  python scripts/run_live.py --strategy revert --min-payout 0.80

Stop with Ctrl+C. Risk limits from .env apply; the kill switch latches if
the daily loss limit is hit. There is no backtest: a strategy is judged only
by the win rate it accumulates here vs the breakeven (~52% at ~92% payout),
and you need a large sample before that number means anything.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import load_settings  # noqa: E402
from src.connector.quotex import QuotexConnector  # noqa: E402
from src.executor import Executor  # noqa: E402
from src.logger import get_logger  # noqa: E402
from src.risk import RiskManager  # noqa: E402
from src.strategies import REGISTRY  # noqa: E402

log = get_logger("run_live")


def run_multi(conn, ex, strat, risk, args) -> None:
    """Sweep the payout watchlist, acting once per closed candle per asset.

    Stops when the risk manager refuses further trades (kill switch OR
    trades/day cap) AND every placed order has resolved, so the run ends
    on its own instead of spinning forever.
    """
    last_ts: dict[str, int] = {}
    watch: list[str] = []
    next_refresh = 0.0

    while True:
        ex.poll_pending()
        ok, why = risk.can_trade()
        if not ok and ex.pending == 0:
            log.info("stopping: %s (all orders settled, day_pnl=%+.2f)",
                     why, risk.day_pnl)
            break

        now = time.time()
        if now >= next_refresh:
            watch = conn.payout_watchlist(args.min_payout)
            if args.max_assets > 0:
                watch = watch[:args.max_assets]
            next_refresh = now + args.refresh
            log.info("watchlist: %d assets payout>=%.0f%% (%s%s)",
                     len(watch), args.min_payout * 100,
                     ", ".join(watch[:6]),
                     " ..." if len(watch) > 6 else "")

        if not watch:
            log.info("no assets above payout threshold; waiting...")
            time.sleep(args.refresh)
            continue

        for asset in watch:
            if not ok:
                break
            candles = conn.candles(asset, args.timeframe, strat.warmup + 10)
            if len(candles) < strat.warmup:
                continue
            ts = int(candles.iloc[-1]["ts"])
            if ts == last_ts.get(asset):
                continue                       # already acted on this candle
            last_ts[asset] = ts
            sig = strat.generate(candles)
            ex.trade(asset, sig, args.expiry_bars * args.timeframe)
            if args.spacing > 0:
                time.sleep(args.spacing)

        time.sleep(max(1, args.timeframe // 4))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", choices=list(REGISTRY), default="revert")
    p.add_argument("--min-payout", type=float, default=0.80,
                   help="trade assets with turbo payout >= this (0-1)")
    p.add_argument("--max-assets", type=int, default=0,
                   help="cap watchlist size (0 = no cap / all)")
    p.add_argument("--refresh", type=int, default=60,
                   help="seconds between watchlist refreshes")
    p.add_argument("--spacing", type=float, default=0.0,
                   help="seconds between placements (0 = best-effort)")
    p.add_argument("--expiry-bars", type=int, default=1)
    p.add_argument("--timeframe", type=int, default=5)
    args = p.parse_args()

    settings = load_settings()               # raises if real requested unsafely
    if not settings.email or not settings.password:
        raise SystemExit("Set QUOTEX_EMAIL / QUOTEX_PASSWORD in .env first "
                          "(copy .env.example to .env).")

    strat = REGISTRY[args.strategy]()
    risk = RiskManager(settings.risk)
    conn = QuotexConnector(settings.email, settings.password,
                           allow_real=settings.is_real)

    log.info("connecting to Quotex (first run may need Cloudflare/2FA)...")
    conn.connect()
    acct = "DEMO" if conn.is_demo else "REAL"
    log.info("connected [%s] balance=%.2f strategy=%s tf=%ss",
             acct, conn.balance(), strat.name, args.timeframe)
    if not conn.is_demo:
        raise SystemExit("Live account is REAL — refusing to run the loop.")

    ex = Executor(conn, risk, settings)
    try:
        run_multi(conn, ex, strat, risk, args)
    except KeyboardInterrupt:
        log.info("interrupted by user")
    finally:
        conn.close()
        log.info("done. trades_pnl=%+.2f", risk.day_pnl)


if __name__ == "__main__":
    main()
