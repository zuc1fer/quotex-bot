"""Connector interface — the ONLY place coupled to Quotex.

Everything else (strategies, risk, executor) depends on this abstraction, not
on the fragile unofficial library. When Quotex changes their protocol, only
quotex.py breaks; the rest of the system keeps working and stays testable.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from src.types import Signal, TradeResult


class Connector(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def is_demo(self) -> bool:
        """Must reflect the ACTUAL account the orders will hit, not config."""
        ...

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def balance(self) -> float: ...

    @abstractmethod
    def candles(self, asset: str, timeframe_sec: int, count: int) -> pd.DataFrame:
        """Return the latest `count` closed candles, oldest first.
        Columns: ts, open, high, low, close, volume.
        """
        ...

    @abstractmethod
    def buy(self, asset: str, signal: Signal, amount: float, duration_sec: int) -> str:
        """Place a fixed-time trade. Returns an order id."""
        ...

    @abstractmethod
    def result(self, order_id: str) -> TradeResult | None:
        """Resolved result, or None if the option has not expired yet."""
        ...
