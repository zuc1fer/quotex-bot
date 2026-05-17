"""Sample strategy: RSI mean-reversion.

CALL when RSI exits oversold (crosses up through `low`), PUT when it exits
overbought (crosses down through `high`). Baseline only — backtest first.
"""
from __future__ import annotations

import pandas as pd

from src.strategies.base import Strategy
from src.types import Signal


def rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    return 100 - (100 / (1 + rs))


class RsiStrategy(Strategy):
    def __init__(self, period: int = 14, low: float = 30.0, high: float = 70.0) -> None:
        self.period = period
        self.low = low
        self.high = high
        self.warmup = period + 2

    @property
    def name(self) -> str:
        return f"rsi({self.period},{self.low},{self.high})"

    def generate(self, candles: pd.DataFrame) -> Signal:
        if len(candles) < self.warmup:
            return Signal.NONE
        r = rsi(candles["close"], self.period)
        prev, curr = r.iloc[-2], r.iloc[-1]
        if pd.isna(prev) or pd.isna(curr):
            return Signal.NONE
        if prev <= self.low < curr:
            return Signal.CALL
        if prev >= self.high > curr:
            return Signal.PUT
        return Signal.NONE
