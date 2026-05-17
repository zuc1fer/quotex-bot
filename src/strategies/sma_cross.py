"""Sample strategy: fast/slow simple-moving-average crossover.

CALL when the fast SMA crosses ABOVE the slow SMA, PUT when it crosses BELOW.
This is a classic baseline — useful to validate the harness, NOT a proven
money-maker. Prove it on the live demo win rate before believing it.
"""
from __future__ import annotations

import pandas as pd

from src.strategies.base import Strategy
from src.types import Signal


class SmaCrossStrategy(Strategy):
    def __init__(self, fast: int = 5, slow: int = 20) -> None:
        if fast >= slow:
            raise ValueError("fast period must be < slow period")
        self.fast = fast
        self.slow = slow
        self.warmup = slow + 1

    @property
    def name(self) -> str:
        return f"sma_cross({self.fast},{self.slow})"

    def generate(self, candles: pd.DataFrame) -> Signal:
        if len(candles) < self.warmup:
            return Signal.NONE
        close = candles["close"]
        fast = close.rolling(self.fast).mean()
        slow = close.rolling(self.slow).mean()

        prev_diff = fast.iloc[-2] - slow.iloc[-2]
        curr_diff = fast.iloc[-1] - slow.iloc[-1]

        if prev_diff <= 0 < curr_diff:
            return Signal.CALL
        if prev_diff >= 0 > curr_diff:
            return Signal.PUT
        return Signal.NONE
