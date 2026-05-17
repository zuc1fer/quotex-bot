"""Mean-reversion fade strategy.

The breakout scalper chased momentum and lost. This takes the opposite
premise: at very short horizons a synthetic feed tends to mean-revert, so
after a run of `streak` candles all in one direction we bet the REVERSAL.

  * `streak` consecutive UP (close>open) candles  -> PUT  (fade the rally)
  * `streak` consecutive DOWN candles             -> CALL (fade the drop)
  * a doji (close==open) breaks the run            -> NONE

NO EDGE IS IMPLIED. This is still trading near-noise against an ~92%-payout
house edge (breakeven ~52%). It is judged solely by the live demo win rate,
not by reasoning about why it "should" work.
"""
from __future__ import annotations

import pandas as pd

from src.strategies.base import Strategy
from src.types import Signal


class RevertStrategy(Strategy):
    def __init__(self, streak: int = 3) -> None:
        if streak < 1:
            raise ValueError("streak must be >= 1")
        self.streak = streak
        self.warmup = streak + 1

    @property
    def name(self) -> str:
        return f"revert({self.streak})"

    def generate(self, candles: pd.DataFrame) -> Signal:
        if len(candles) < self.warmup:
            return Signal.NONE

        last = candles.iloc[-self.streak:]
        dirs = (last["close"] - last["open"]).tolist()

        if all(d > 0 for d in dirs):
            return Signal.PUT          # fade the up-run
        if all(d < 0 for d in dirs):
            return Signal.CALL         # fade the down-run
        return Signal.NONE
