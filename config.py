"""Central config + the hard demo-by-default safety guard.

Real-money trading is gated behind TWO independent switches so it can never
be entered by accident:
  1. QUOTEX_ACCOUNT_MODE must equal "real"
  2. QUOTEX_ALLOW_REAL must equal the exact opt-in token

If only one is set, we fail loudly and stay on demo.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv

load_dotenv()

REAL_OPT_IN_TOKEN = "I_UNDERSTAND_REAL_MONEY_RISK"


class AccountMode(str, Enum):
    DEMO = "demo"
    REAL = "real"


class UnsafeRealModeError(RuntimeError):
    """Raised when real mode is requested without the explicit opt-in token."""


@dataclass(frozen=True)
class RiskConfig:
    stake_per_trade: float
    max_daily_loss: float
    max_trades_per_day: int


@dataclass(frozen=True)
class Settings:
    email: str
    password: str
    account_mode: AccountMode
    real_allowed: bool
    risk: RiskConfig

    @property
    def is_real(self) -> bool:
        """True only if real mode is requested AND explicitly opted in."""
        return self.account_mode is AccountMode.REAL and self.real_allowed


def load_settings() -> Settings:
    requested = os.getenv("QUOTEX_ACCOUNT_MODE", "demo").strip().lower()
    opt_in = os.getenv("QUOTEX_ALLOW_REAL", "").strip()
    real_allowed = opt_in == REAL_OPT_IN_TOKEN

    if requested == AccountMode.REAL.value and not real_allowed:
        raise UnsafeRealModeError(
            "QUOTEX_ACCOUNT_MODE=real but QUOTEX_ALLOW_REAL is not set to the "
            f"exact token '{REAL_OPT_IN_TOKEN}'. Refusing to run with real "
            "money. Staying safe — fix .env or switch back to demo."
        )

    mode = AccountMode.REAL if requested == AccountMode.REAL.value else AccountMode.DEMO

    return Settings(
        email=os.getenv("QUOTEX_EMAIL", ""),
        password=os.getenv("QUOTEX_PASSWORD", ""),
        account_mode=mode,
        real_allowed=real_allowed,
        risk=RiskConfig(
            stake_per_trade=float(os.getenv("RISK_STAKE_PER_TRADE", "1.0")),
            max_daily_loss=float(os.getenv("RISK_MAX_DAILY_LOSS", "10.0")),
            max_trades_per_day=int(os.getenv("RISK_MAX_TRADES_PER_DAY", "20")),
        ),
    )
