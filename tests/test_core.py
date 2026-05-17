import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import RiskConfig
from src.risk import RiskManager
from src.strategies import RevertStrategy, SmaCrossStrategy
from src.types import Signal


def _flat_candles(n: int) -> pd.DataFrame:
    """Minimal OHLC frame for exercising strategy plumbing without a feed."""
    return pd.DataFrame({
        "ts": range(n),
        "open": [1.0] * n, "high": [1.0] * n,
        "low": [1.0] * n, "close": [1.0] * n, "volume": [0.0] * n,
    })


def _dir_candles(deltas: list[float]) -> pd.DataFrame:
    """Frame where each bar's (close-open) sign is the given delta sign."""
    n = len(deltas)
    return pd.DataFrame({
        "ts": range(n),
        "open": [1.0] * n,
        "high": [1.0 + abs(d) for d in deltas],
        "low": [1.0 - abs(d) for d in deltas],
        "close": [1.0 + d for d in deltas],
        "volume": [0.0] * n,
    })


def test_strategy_returns_none_before_warmup():
    s = SmaCrossStrategy(fast=5, slow=20)
    assert s.generate(_flat_candles(10)) is Signal.NONE   # warmup = slow + 1


def test_revert_none_before_warmup():
    s = RevertStrategy(streak=3)                           # warmup = 4
    assert s.generate(_dir_candles([0.1, 0.1])) is Signal.NONE


def test_revert_fades_up_run_with_put():
    s = RevertStrategy(streak=3)
    assert s.generate(_dir_candles([-0.1, 0.1, 0.1, 0.1])) is Signal.PUT


def test_revert_fades_down_run_with_call():
    s = RevertStrategy(streak=3)
    assert s.generate(_dir_candles([0.1, -0.1, -0.1, -0.1])) is Signal.CALL


def test_revert_none_when_run_broken():
    s = RevertStrategy(streak=3)
    # last 3 are up, down, up -> not a clean run
    assert s.generate(_dir_candles([0.1, 0.1, -0.1, 0.1])) is Signal.NONE


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
