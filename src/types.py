"""Shared domain types. No external deps so everything can import this."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Signal(str, Enum):
    """A strategy's decision for the next expiry."""
    CALL = "call"   # bet price goes UP
    PUT = "put"     # bet price goes DOWN
    NONE = "none"   # no trade


@dataclass(frozen=True)
class Candle:
    ts: int       # unix seconds (open time)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class TradeResult:
    ts: int
    asset: str
    signal: Signal
    stake: float
    entry_price: float
    exit_price: float
    payout_rate: float          # e.g. 0.85 == 85% profit on a win
    won: bool
    pnl: float                  # +stake*payout_rate on win, -stake on loss
