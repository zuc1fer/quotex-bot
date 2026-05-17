"""Live loop.

  --connector sim     SimulatedConnector — no network/money (default; safe)
  --connector quotex  REAL Quotex via vendored pyquotex, DEMO account

Demo-gated end to end: config.py refuses unsafe real mode, QuotexConnector
forces PRACTICE and re-checks the live account on every order, executor.py
blocks real orders without explicit opt-in.

  python scripts/run_live.py --connector quotex --asset EURUSD_otc --strategy rsi
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import load_settings  # noqa: E402
from src.connector.simulated import SimulatedConnector  # noqa: E402
from src.executor import Executor  # noqa: E402
from src.logger import get_logger  # noqa: E402
from src.risk import RiskManager  # noqa: E402
from src.strategies import REGISTRY  # noqa: E402

log = get_logger("run_live")


def run_sim(conn, ex, strat, risk, args) -> None:
    while conn.step():
        ex.poll_pending()
        if risk.tripped:
            log.warning("kill switch tripped - stopping")
            break
        candles = conn.candles(args.asset, args.timeframe, strat.warmup + 5)
        if len(candles) >= strat.warmup:
            ex.trade(args.asset, strat.generate(candles),
                     args.expiry_bars * args.timeframe)
    ex.poll_pending()


def run_realtime(conn, ex, strat, risk, args) -> None:
    """One decision per fresh candle, in wall-clock real time."""
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
    p.add_argument("--connector", choices=["sim", "quotex"], default="sim")
    p.add_argument("--strategy", choices=list(REGISTRY), default="sma_cross")
    p.add_argument("--asset", default="EURUSD_otc")
    p.add_argument("--expiry-bars", type=int, default=1)
    p.add_argument("--timeframe", type=int, default=60)
    args = p.parse_args()

    settings = load_settings()               # raises if real requested unsafely
    strat = REGISTRY[args.strategy]()
    risk = RiskManager(settings.risk)

    if args.connector == "quotex":
        from src.connector.quotex import QuotexConnector
        conn = QuotexConnector(settings.email, settings.password,
                               allow_real=settings.is_real)
    else:
        conn = SimulatedConnector(timeframe_sec=args.timeframe)

    conn.connect()
    ex = Executor(conn, risk, settings)
    log.info("connector=%s is_demo=%s strategy=%s asset=%s",
             conn.name, conn.is_demo, strat.name, args.asset)

    try:
        if args.connector == "quotex":
            run_realtime(conn, ex, strat, risk, args)
        else:
            run_sim(conn, ex, strat, risk, args)
    except KeyboardInterrupt:
        log.info("interrupted by user")
    finally:
        if hasattr(conn, "close"):
            conn.close()
        log.info("done. trades_pnl=%+.2f", risk.day_pnl)


if __name__ == "__main__":
    main()
