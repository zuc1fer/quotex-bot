"""Prove (or disprove) a strategy BEFORE it touches Quotex.

  python scripts/run_backtest.py                       # all strategies, synthetic
  python scripts/run_backtest.py --strategy sma_cross --csv data/eurusd.csv
  python scripts/run_backtest.py --payout 0.85 --expiry-bars 1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from src.backtest import run_backtest  # noqa: E402
from src.connector.simulated import synthetic_series  # noqa: E402
from src.strategies import REGISTRY  # noqa: E402


def load_df(csv: str | None) -> pd.DataFrame:
    if csv:
        df = pd.read_csv(csv)
        need = {"ts", "open", "high", "low", "close"}
        missing = need - set(df.columns)
        if missing:
            raise SystemExit(f"CSV missing columns: {missing}")
        if "volume" not in df:
            df["volume"] = 0.0
        return df
    return synthetic_series()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", choices=list(REGISTRY), default=None)
    p.add_argument("--csv", default=None, help="OHLC csv; omitted => synthetic")
    p.add_argument("--payout", type=float, default=0.85)
    p.add_argument("--expiry-bars", type=int, default=1)
    p.add_argument("--stake", type=float, default=1.0)
    args = p.parse_args()

    df = load_df(args.csv)
    src = args.csv or "synthetic random walk"
    print(f"data: {src}  ({len(df)} candles)\n")

    names = [args.strategy] if args.strategy else list(REGISTRY)
    for name in names:
        strat = REGISTRY[name]()
        res = run_backtest(strat, df, payout_rate=args.payout,
                           expiry_bars=args.expiry_bars, stake=args.stake)
        print(res.summary(), "\n")

    if not args.csv:
        print("NOTE: synthetic data is random by construction. Any 'edge' here "
              "is noise.\nFeed real Quotex candles via --csv for a real test.")


if __name__ == "__main__":
    main()
