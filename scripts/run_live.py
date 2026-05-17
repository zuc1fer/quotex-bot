"""Live loop on Quotex — DEMO account only.

Connects to the real Quotex WebSocket via the vendored pyquotex client, but is
demo-gated end to end: config.py refuses unsafe real mode, QuotexConnector
forces the PRACTICE account and re-checks the live account on every order, and
executor.py blocks any real-money order without explicit opt-in.

One decision per freshly-closed candle, in wall-clock real time. There is no
backtest and no simulated feed: a strategy is judged by the win rate it
accumulates here, on Quotex's actual feed, versus the breakeven win rate
(~54% at an 85% payout). You need ~100+ trades before that number means
anything.

  python scripts/run_live.py --asset EURUSD_otc --strategy rsi

Stop with Ctrl+C. Risk limits from .env (stake / daily-loss / trades-per-day)
apply and the kill switch latches if the daily loss limit is hit.
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


def run_realtime(conn, ex, strat, risk, args) -> None:
    """Act once per closed candle, polling pending results in between."""
    last_ts = None
    while True:
        ex.poll_pending()
        if risk.tripped:
            log.warning("kill switch tripped - stopping")
            break
        candles = conn.candles(args.asset, args.timeframe, strat.warmup + 10)
        if len(candles) < strat.warmup:
            log.info("waiting for candle data...")
            time.sleep(args.timeframe)
            continue
        ts = int(candles.iloc[-1]["ts"])
        if ts != last_ts:                       # act once per closed candle
            last_ts = ts
            sig = strat.generate(candles)
            ex.trade(args.asset, sig, args.expiry_bars * args.timeframe)
        time.sleep(max(1, args.timeframe // 4))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", choices=list(REGISTRY), default="rsi")
    p.add_argument("--asset", default="EURUSD_otc",
                   help="_otc assets trade 24/7; non-OTC follow FX hours")
    p.add_argument("--expiry-bars", type=int, default=1)
    p.add_argument("--timeframe", type=int, default=60)
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
    log.info("connected [%s] balance=%.2f strategy=%s asset=%s",
             acct, conn.balance(), strat.name, args.asset)
    if not conn.is_demo:
        # QuotexConnector already refuses this unless explicitly opted in;
        # this is a last visible stop before the loop.
        raise SystemExit("Live account is REAL — refusing to run the loop.")

    ex = Executor(conn, risk, settings)
    try:
        run_realtime(conn, ex, strat, risk, args)
    except KeyboardInterrupt:
        log.info("interrupted by user")
    finally:
        conn.close()
        log.info("done. trades_pnl=%+.2f", risk.day_pnl)


if __name__ == "__main__":
    main()
