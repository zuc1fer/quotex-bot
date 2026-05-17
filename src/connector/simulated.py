"""Offline connector: synthetic or CSV price feed, paper trades only.

Use this for backtests and for developing the live loop with ZERO money and
ZERO network. is_demo is hard-coded True — it physically cannot touch a real
account.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.connector.base import Connector
from src.types import Signal, TradeResult


def synthetic_series(n: int = 3000, seed: int | None = 42,
                      start: float = 1.10, vol: float = 0.0008) -> pd.DataFrame:
    """A random walk shaped like FX 1-minute OHLC. Random by construction —
    no strategy should be profitable on this. That is the point: it is the
    null hypothesis your backtest must beat."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0, vol, n)
    close = start + np.cumsum(steps)
    open_ = np.concatenate([[start], close[:-1]])
    noise = np.abs(rng.normal(0, vol, n))
    high = np.maximum(open_, close) + noise
    low = np.minimum(open_, close) - noise
    ts = np.arange(n, dtype=np.int64) * 60
    return pd.DataFrame(
        {"ts": ts, "open": open_, "high": high, "low": low,
         "close": close, "volume": np.zeros(n)}
    )


class SimulatedConnector(Connector):
    def __init__(self, df: pd.DataFrame | None = None, *,
                 payout_rate: float = 0.85, timeframe_sec: int = 60,
                 warmup: int = 50) -> None:
        self._df = df if df is not None else synthetic_series()
        self._payout = payout_rate
        self._tf = timeframe_sec
        self._i = warmup                # cursor: index of latest CLOSED candle
        self._orders: dict[str, dict] = {}
        self._seq = 0

    @property
    def name(self) -> str:
        return "simulated"

    @property
    def is_demo(self) -> bool:
        return True

    def connect(self) -> None:
        pass

    def balance(self) -> float:
        return 10_000.0

    def candles(self, asset: str, timeframe_sec: int, count: int) -> pd.DataFrame:
        lo = max(0, self._i - count + 1)
        return self._df.iloc[lo:self._i + 1].reset_index(drop=True)

    def step(self) -> bool:
        """Advance one candle. Returns False when the series is exhausted."""
        if self._i + 1 >= len(self._df):
            return False
        self._i += 1
        return True

    def buy(self, asset: str, signal: Signal, amount: float, duration_sec: int) -> str:
        self._seq += 1
        oid = f"sim-{self._seq}"
        bars = max(1, duration_sec // self._tf)
        self._orders[oid] = {
            "asset": asset, "signal": signal, "amount": amount,
            "entry_i": self._i, "expiry_i": self._i + bars,
            "entry_price": float(self._df.iloc[self._i]["close"]),
        }
        return oid

    def result(self, order_id: str) -> TradeResult | None:
        o = self._orders[order_id]
        if self._i < o["expiry_i"]:
            return None
        exit_price = float(self._df.iloc[o["expiry_i"]]["close"])
        if o["signal"] is Signal.CALL:
            won = exit_price > o["entry_price"]
        else:
            won = exit_price < o["entry_price"]
        pnl = o["amount"] * self._payout if won else -o["amount"]
        return TradeResult(
            ts=int(self._df.iloc[o["entry_i"]]["ts"]), asset=o["asset"],
            signal=o["signal"], stake=o["amount"],
            entry_price=o["entry_price"], exit_price=exit_price,
            payout_rate=self._payout, won=won, pnl=pnl,
        )
