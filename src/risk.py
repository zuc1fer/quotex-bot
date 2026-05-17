"""Risk manager. Applies in BOTH demo and real — habits built on demo are
the ones that run on real money later.

Hard stops: per-trade stake cap, max trades/day, max daily loss. Once the
daily loss limit is hit the kill switch trips and stays tripped until reset.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config import RiskConfig


@dataclass
class RiskManager:
    cfg: RiskConfig
    _day_pnl: float = 0.0
    _day_trades: int = 0
    _tripped: bool = field(default=False)

    @property
    def tripped(self) -> bool:
        return self._tripped

    @property
    def day_pnl(self) -> float:
        return self._day_pnl

    def can_trade(self) -> tuple[bool, str]:
        if self._tripped:
            return False, "kill switch tripped (daily loss limit reached)"
        if self._day_trades >= self.cfg.max_trades_per_day:
            return False, f"max trades/day reached ({self.cfg.max_trades_per_day})"
        if -self._day_pnl >= self.cfg.max_daily_loss:
            self._tripped = True
            return False, f"daily loss limit reached ({self.cfg.max_daily_loss})"
        return True, "ok"

    def stake(self) -> float:
        return self.cfg.stake_per_trade

    def register(self, pnl: float) -> None:
        self._day_pnl += pnl
        self._day_trades += 1
        if -self._day_pnl >= self.cfg.max_daily_loss:
            self._tripped = True

    def reset_day(self) -> None:
        self._day_pnl = 0.0
        self._day_trades = 0
        self._tripped = False
