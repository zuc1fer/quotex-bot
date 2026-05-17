"""The safety guards are the most important tests in this repo."""
import importlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _reload_config():
    import config
    return importlib.reload(config)


def test_demo_is_default(monkeypatch):
    monkeypatch.delenv("QUOTEX_ACCOUNT_MODE", raising=False)
    monkeypatch.delenv("QUOTEX_ALLOW_REAL", raising=False)
    cfg = _reload_config()
    s = cfg.load_settings()
    assert s.account_mode is cfg.AccountMode.DEMO
    assert s.is_real is False


def test_real_without_token_raises(monkeypatch):
    monkeypatch.setenv("QUOTEX_ACCOUNT_MODE", "real")
    monkeypatch.delenv("QUOTEX_ALLOW_REAL", raising=False)
    cfg = _reload_config()
    with pytest.raises(cfg.UnsafeRealModeError):
        cfg.load_settings()


def test_real_with_wrong_token_raises(monkeypatch):
    monkeypatch.setenv("QUOTEX_ACCOUNT_MODE", "real")
    monkeypatch.setenv("QUOTEX_ALLOW_REAL", "yes")
    cfg = _reload_config()
    with pytest.raises(cfg.UnsafeRealModeError):
        cfg.load_settings()


def test_real_requires_exact_token(monkeypatch):
    monkeypatch.setenv("QUOTEX_ACCOUNT_MODE", "real")
    monkeypatch.setenv("QUOTEX_ALLOW_REAL", "I_UNDERSTAND_REAL_MONEY_RISK")
    cfg = _reload_config()
    s = cfg.load_settings()
    assert s.is_real is True


def test_executor_blocks_real_when_not_opted_in(monkeypatch):
    monkeypatch.delenv("QUOTEX_ACCOUNT_MODE", raising=False)
    monkeypatch.delenv("QUOTEX_ALLOW_REAL", raising=False)
    cfg = _reload_config()
    from src.executor import Executor, RealMoneyBlocked
    from src.risk import RiskManager
    from src.types import Signal

    class FakeRealConn:
        is_demo = False
        def buy(self, *a, **k): return "x"
        def result(self, _): return None

    s = cfg.load_settings()
    ex = Executor(FakeRealConn(), RiskManager(s.risk), s)
    with pytest.raises(RealMoneyBlocked):
        ex.trade("EURUSD", Signal.CALL, 60)
