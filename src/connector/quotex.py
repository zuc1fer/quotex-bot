"""Real Quotex connector — unofficial WebSocket, demo-gated.

Wraps the VENDORED pyquotex client (vendor/pyquotex). pyquotex is fully
async; the rest of this project is sync, so we run one asyncio event loop in a
daemon thread and marshal coroutines onto it. That keeps the websocket alive
across calls while the executor/strategy code stays unchanged.

SAFETY MODEL (read this):
  * We force the PRACTICE (demo) account before AND after connect.
  * is_demo reflects the LIVE session's account (client.account_is_demo),
    never our config — so a misconfig cannot silently route to real funds.
  * Constructing with allow_real=False (the default) makes connect() raise
    if the live account is anything other than DEMO.
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time
from concurrent.futures import Future
from pathlib import Path

import pandas as pd

from src.connector.base import Connector
from src.logger import get_logger
from src.types import Signal, TradeResult

# Make the vendored package importable.
_VENDOR = Path(__file__).resolve().parents[2] / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from pyquotex.stable_api import Quotex  # noqa: E402
from pyquotex.utils.account_type import AccountType  # noqa: E402

log = get_logger("quotex")


class _LoopThread:
    """A private asyncio event loop running in a daemon thread."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro, timeout: float | None = None):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def spawn(self, coro) -> Future:
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)


class QuotexConnector(Connector):
    def __init__(self, email: str, password: str, *,
                 allow_real: bool = False, lang: str = "en") -> None:
        if not email or not password:
            raise ValueError("Quotex email/password required (set them in .env)")
        self._email = email
        self._password = password
        self._allow_real = allow_real
        self._lang = lang
        self._loop = _LoopThread()
        self._client: Quotex | None = None
        self._connected = False
        # order_id -> {future, asset, signal, stake, entry_price, payout}
        self._orders: dict[str, dict] = {}

    @property
    def name(self) -> str:
        return "quotex"

    @property
    def is_demo(self) -> bool:
        """LIVE account state. Defaults to True (safe) until connected."""
        if self._client is None:
            return True
        return int(self._client.account_is_demo) == int(AccountType.DEMO)

    def connect(self) -> None:
        client = Quotex(email=self._email, password=self._password,
                         lang=self._lang)
        client.set_account_mode("PRACTICE")          # demo BEFORE connect
        self._client = client

        ok, reason = self._loop.run(client.connect(), timeout=90)
        if not ok:
            raise ConnectionError(
                f"Quotex connect failed: {reason}. (First login may need a "
                "Cloudflare/2FA step — see README troubleshooting.)"
            )

        self._loop.run(client.change_account("PRACTICE"), timeout=30)  # force demo

        if not self.is_demo and not self._allow_real:
            self._loop.run(client.close(), timeout=10)
            raise RuntimeError(
                "Live Quotex account is REAL but allow_real=False. Refusing "
                "to proceed. (Demo-by-default guard — your funds are safe.)"
            )

        self._connected = True
        acct = "DEMO" if self.is_demo else "REAL"
        log.info("connected to Quotex [%s]", acct)

    def _ensure(self) -> Quotex:
        if not self._connected or self._client is None:
            raise RuntimeError("not connected — call connect() first")
        return self._client

    def balance(self) -> float:
        return float(self._loop.run(self._ensure().get_balance(), timeout=30))

    def candles(self, asset: str, timeframe_sec: int, count: int) -> pd.DataFrame:
        client = self._ensure()
        raw = self._loop.run(
            client.get_candles(asset, time.time(),
                               timeframe_sec * (count + 2), timeframe_sec),
            timeout=60,
        ) or []
        rows = [
            {"ts": int(c["time"]), "open": float(c["open"]),
             "high": float(c["high"]), "low": float(c["low"]),
             "close": float(c["close"]), "volume": float(c.get("volume", 0) or 0)}
            for c in raw if c.get("open") is not None
        ]
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low",
                                         "close", "volume"])
        return df.sort_values("ts").reset_index(drop=True)

    def buy(self, asset: str, signal: Signal, amount: float,
            duration_sec: int) -> str:
        client = self._ensure()
        # Hard re-check the live account on EVERY order, not just at connect.
        if not self.is_demo and not self._allow_real:
            raise RuntimeError("live account is REAL and allow_real=False — "
                               "order refused")

        direction = "call" if signal is Signal.CALL else "put"
        status, info = self._loop.run(
            client.buy(amount, asset, direction, duration_sec),
            timeout=duration_sec + 30,
        )
        if not status or not isinstance(info, dict):
            raise RuntimeError(f"buy rejected by Quotex: {info}")

        oid = str(info.get("id"))
        entry = float(info.get("openPrice") or info.get("open_price") or 0.0)
        # Resolve the win/loss asynchronously so result() stays non-blocking.
        fut = self._loop.spawn(client.check_win(info.get("id"), duration_sec))
        self._orders[oid] = {
            "future": fut, "asset": asset, "signal": signal,
            "stake": amount, "entry_price": entry,
        }
        return oid

    def result(self, order_id: str) -> TradeResult | None:
        o = self._orders.get(order_id)
        if o is None:
            return None
        fut: Future = o["future"]
        if not fut.done():
            return None

        win_str, profit = fut.result()
        won = str(win_str).lower() == "win"
        stake = o["stake"]
        if won:
            pnl = float(profit)
            payout = (pnl / stake) if stake else 0.0
        elif str(win_str).lower() in ("equal", "doji", "tie"):
            pnl, payout = 0.0, 0.0
        else:
            pnl, payout = -stake, 0.0

        del self._orders[order_id]
        return TradeResult(
            ts=int(time.time()), asset=o["asset"], signal=o["signal"],
            stake=stake, entry_price=o["entry_price"],
            exit_price=o["entry_price"],   # broker pnl is authoritative
            payout_rate=payout, won=won, pnl=pnl,
        )

    def close(self) -> None:
        if self._client is not None:
            try:
                self._loop.run(self._client.close(), timeout=10)
            except Exception:
                pass
        self._loop.stop()
        self._connected = False
