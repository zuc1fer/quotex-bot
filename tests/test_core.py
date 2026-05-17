import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import RiskConfig
from src.backtest import run_backtest
from src.connector.simulated import synthetic_series
from src.risk import RiskManager
from src.strategies import SmaCrossStrategy
from src.types import Signal


def test_breakeven_math():
    df = synthetic_series(n=500)
    res = run_backtest(SmaCrossStrategy(), df, payout_rate=0.85)
    assert abs(res.breakeven_win_rate - 1 / 1.85) < 1e-9


def test_no_lookahead_signal_uses_only_past():
    # Strategy must return NONE before warmup is satisfied.
    s = SmaCrossStrategy(fast=5, slow=20)
    df = synthetic_series(n=10)
    assert s.generate(df) is Signal.NONE


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


def test_backtest_runs_and_counts():
    df = synthetic_series(n=1000)
    res = run_backtest(SmaCrossStrategy(), df, payout_rate=0.85, expiry_bars=1)
    assert res.trades >= 0
    assert res.wins <= res.trades
