import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import RiskConfig
from src.risk import RiskManager
from src.strategies import SmaCrossStrategy
from src.types import Signal


def _flat_candles(n: int) -> pd.DataFrame:
    """Minimal OHLC frame for exercising strategy plumbing without a feed."""
    return pd.DataFrame({
        "ts": range(n),
        "open": [1.0] * n, "high": [1.0] * n,
        "low": [1.0] * n, "close": [1.0] * n, "volume": [0.0] * n,
    })


def test_strategy_returns_none_before_warmup():
    s = SmaCrossStrategy(fast=5, slow=20)
    assert s.generate(_flat_candles(10)) is Signal.NONE   # warmup = slow + 1


def test_risk_kill_switch_trips_on_daily_loss():
    rm = RiskManager(RiskConfig(stake_per_trade=1.0, max_daily_loss=3.0,
                                max_trades_per_day=100))
    for _ in range(3):
        ok, _ = rm.can_trade()
        assert ok
        rm.register(-1.0)
    ok, why = rm.can_trade()
    assert not ok and rm.tripped


def test_risk_caps_trades_per_day():
    rm = RiskManager(RiskConfig(stake_per_trade=1.0, max_daily_loss=999.0,
                                max_trades_per_day=2))
    rm.register(1.0)
    rm.register(1.0)
    ok, why = rm.can_trade()
    assert not ok and "max trades" in why
