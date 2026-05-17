"""Binary-options backtester.

PnL model per trade: stake at risk; win => +stake * payout_rate, lose =>
-stake. The decisive number is the BREAKEVEN WIN RATE:

    breakeven = 1 / (1 + payout_rate)

At payout 0.85 you must win > 54.05% of trades just to not lose money. A
coin-flip (50%) bleeds out. This is why "the bot works" is a claim about
win rate vs. this threshold — not about whether the code runs.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base import Strategy
from src.types import Signal


@dataclass
class BacktestResult:
    strategy: str
    trades: int
    wins: int
    payout_rate: float
    total_pnl: float
    max_drawdown: float

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    @property
    def breakeven_win_rate(self) -> float:
        return 1.0 / (1.0 + self.payout_rate)

    @property
    def has_edge(self) -> bool:
        return self.trades > 0 and self.win_rate > self.breakeven_win_rate

    def summary(self) -> str:
        if not self.trades:
            return f"{self.strategy}: no trades generated."
        verdict = "EDGE (on this data)" if self.has_edge else "NO EDGE - loses money"
        return (
            f"{self.strategy}\n"
            f"  trades={self.trades}  wins={self.wins}  "
            f"win_rate={self.win_rate:.2%}\n"
            f"  breakeven needed={self.breakeven_win_rate:.2%} "
            f"(payout {self.payout_rate:.0%})\n"
            f"  total_pnl={self.total_pnl:+.2f}  "
            f"max_drawdown={self.max_drawdown:.2f}\n"
            f"  verdict: {verdict}"
        )


def run_backtest(strategy: Strategy, df: pd.DataFrame, *,
                 payout_rate: float = 0.85, expiry_bars: int = 1,
                 stake: float = 1.0) -> BacktestResult:
    """Walk the series bar by bar with NO look-ahead: decide on candles
    [0..i], settle against close[i + expiry_bars]."""
    trades = wins = 0
    pnl = 0.0
    peak = 0.0
    max_dd = 0.0
    last = len(df) - expiry_bars

    for i in range(strategy.warmup, last):
        window = df.iloc[: i + 1]
        sig = strategy.generate(window)
        if sig is Signal.NONE:
            continue
        entry = float(df.iloc[i]["close"])
        exit_ = float(df.iloc[i + expiry_bars]["close"])
        won = exit_ > entry if sig is Signal.CALL else exit_ < entry
        pnl += stake * payout_rate if won else -stake
        trades += 1
        wins += int(won)
        peak = max(peak, pnl)
        max_dd = max(max_dd, peak - pnl)

    return BacktestResult(
        strategy=strategy.name, trades=trades, wins=wins,
        payout_rate=payout_rate, total_pnl=pnl, max_drawdown=max_dd,
    )
