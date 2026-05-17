"""Trade executor: the second, independent real-money guard.

config.py guards mode selection. This guards every individual order: if the
connector is on a REAL account and the explicit opt-in is not set, the order
is refused here — even if something upstream went wrong.
"""
from __future__ import annotations

from config import Settings
from src.connector.base import Connector
from src.logger import get_logger
from src.risk import RiskManager
from src.types import Signal, TradeResult

try:                                      # connector-specific, optional
    from src.connector.quotex import OrderIdCollision
except Exception:                         # pragma: no cover
    class OrderIdCollision(RuntimeError):
        ...

log = get_logger("executor")


class RealMoneyBlocked(RuntimeError):
    pass


class Executor:
    def __init__(self, connector: Connector, risk: RiskManager,
                 settings: Settings) -> None:
        self.c = connector
        self.risk = risk
        self.s = settings
        self._pending: list[str] = []

    @property
    def pending(self) -> int:
        """Orders placed but not yet resolved."""
        return len(self._pending)

    def _assert_safe(self) -> None:
        if not self.c.is_demo and not self.s.is_real:
            raise RealMoneyBlocked(
                "Connector is on a REAL account but real mode is not "
                "explicitly opted in. Order refused. (Demo-by-default guard.)"
            )

    def trade(self, asset: str, signal: Signal, duration_sec: int) -> str | None:
        """Place an order. Fixed-time options settle in the FUTURE, so this
        returns an order id; call poll_pending() later to collect results."""
        if signal is Signal.NONE:
            return None

        ok, why = self.risk.can_trade()
        if not ok:
            log.warning("trade skipped: %s", why)
            return None

        self._assert_safe()

        amount = self.risk.stake()
        acct = "DEMO" if self.c.is_demo else "REAL"
        log.info("[%s] %s %s stake=%.2f dur=%ss",
                 acct, signal.value.upper(), asset, amount, duration_sec)

        try:
            oid = self.c.buy(asset, signal, amount, duration_sec)
        except OrderIdCollision as e:
            # Known best-effort-concurrent noise: do NOT count it.
            log.warning("trade dropped: %s", e)
            return None
        self._pending.append(oid)
        return oid

    def poll_pending(self) -> list[TradeResult]:
        """Resolve any expired orders; register their P&L with the risk mgr."""
        done: list[TradeResult] = []
        still: list[str] = []
        is_pending = getattr(self.c, "is_pending", None)
        for oid in self._pending:
            res = self.c.result(oid)
            if res is None:
                # Keep waiting, unless the connector has dropped it as a
                # stale/voided order (then it must not block forever).
                if is_pending is None or is_pending(oid):
                    still.append(oid)
                continue
            self.risk.register(res.pnl)
            log.info("result %s pnl=%+.2f day_pnl=%+.2f",
                     "WIN" if res.won else "LOSS", res.pnl, self.risk.day_pnl)
            done.append(res)
        self._pending = still
        return done
