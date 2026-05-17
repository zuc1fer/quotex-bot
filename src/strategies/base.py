"""Strategy interface.

A strategy is a PURE function of price history -> Signal. No I/O, no network,
no state about money. That purity keeps it unit-testable and keeps the trading
decision fully separated from the fragile Quotex connector.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from src.types import Signal


class Strategy(ABC):
    #: Minimum number of candles required before the strategy can emit a signal.
    warmup: int = 1

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def generate(self, candles: pd.DataFrame) -> Signal:
        """Given OHLCV history (oldest first, last row = latest CLOSED candle),
        return the decision for the NEXT bar.

        Must not look ahead: only use rows up to and including the last one.
        """
        ...
