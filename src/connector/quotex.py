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
from collections import deque
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

# Grace after the option's own duration before an unresolved order is
# dropped (not counted) rather than waited on forever.
_STALE_GRACE_SEC = 180


class OrderIdCollision(RuntimeError):
    """pyquotex returned an id we are already tracking (rapid-fire race)."""


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
        # order_id -> {raw_id, asset, signal, stake, entry_price, placed, ...}
        self._orders: dict[str, dict] = {}
        # Recently resolved ids — guards against the lib reusing a stale id
        # right after we delete it (bounded FIFO).
        self._recent_ids: deque[str] = deque(maxlen=256)

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
        # time_mode="TIMER" => optionType 100, expiration sent as the RAW
        # duration in seconds. The default "TIME" is a "fast option" whose
        # expiry pyquotex snaps to the next clock-minute, so a requested 5s
        # actually settled in ~60s. TIMER honors the duration literally.
        status, info = self._loop.run(
            client.buy(amount, asset, direction, duration_sec,
                       time_mode="TIMER"),
            timeout=duration_sec + 30,
        )
        if not status or not isinstance(info, dict):
            raise RuntimeError(f"buy rejected by Quotex: {info}")

        raw_id = info.get("id")
        oid = str(raw_id)
        # pyquotex correlates buy confirmations via shared state, so rapid
        # placements can hand back a duplicate/stale id. Refuse to overwrite
        # a live order — the colliding placement is dropped and logged as
        # KNOWN noise rather than silently corrupting another order's stats.
        if oid in self._orders or oid in self._recent_ids:
            raise OrderIdCollision(
                f"duplicate order id {oid} for {asset} {direction} "
                "(rapid-fire collision) — placement dropped, not counted")
        entry = float(info.get("openPrice") or info.get("open_price") or 0.0)
        # No check_win: api._on_message already records the AUTHORITATIVE
        # closed-deal profit into client.api.listinfodata for every deal
        # (same number the Quotex history list shows). We read that in
        # result() and NEVER synthesise a loss on timeout.
        self._orders[oid] = {
            "raw_id": raw_id, "asset": asset, "signal": signal,
            "stake": amount, "entry_price": entry,
            "placed": time.monotonic(), "duration": duration_sec,
        }
        return oid

    def is_pending(self, order_id: str) -> bool:
        """True while we are still tracking this order (not yet resolved
        and not dropped as stale). Lets the caller drop voided orders."""
        return order_id in self._orders

    def result(self, order_id: str) -> TradeResult | None:
        o = self._orders.get(order_id)
        if o is None:
            return None

        lid = self._client.api.listinfodata
        info = lid.get(o["raw_id"]) or lid.get(order_id)

        if not info or info.get("game_state") != 1:
            # Not closed yet. Only drop (never fabricate a loss) if the deal
            # has not resolved long after it should have — a dropped order is
            # excluded from P&L, not counted as a loss.
            waited = time.monotonic() - o["placed"]
            if waited > o["duration"] + _STALE_GRACE_SEC:
                log.warning("order %s unresolved after %.0fs — dropping "
                            "(NOT counted in stats)", order_id, waited)
                del self._orders[order_id]
                self._recent_ids.append(order_id)
            return None

        profit = float(info.get("profit") or 0.0)
        won = str(info.get("win", "")).lower() == "win" or profit > 0.0
        stake = o["stake"]
        payout = (profit / stake) if (won and stake) else 0.0

        lid.delete(o["raw_id"])
        lid.delete(order_id)
        del self._orders[order_id]
        self._recent_ids.append(order_id)
        return TradeResult(
            ts=int(time.time()), asset=o["asset"], signal=o["signal"],
            stake=stake, entry_price=o["entry_price"],
            exit_price=o["entry_price"],   # broker profit is authoritative
            payout_rate=payout, won=won, pnl=profit,
        )

    def payout_watchlist(self, min_payout: float = 0.80) -> list[str]:
        """Open asset symbols whose short-trade (turbo) payout >= min_payout.

        Reads the live instruments table: i[1]=symbol, i[5]=payment %,
        i[14]=open flag, i[18]=turbo (fast/short) payout %. We trade 5s
        TIMER options, so turbo is the relevant payout.
        """
        client = self._ensure()
        inst = getattr(client.api, "instruments", None) or []
        thr = min_payout * 100.0
        out: list[str] = []
        for i in inst:
            try:
                sym, is_open, turbo = i[1], i[14], i[18]
            except (IndexError, TypeError):
                continue
            if is_open and float(turbo or 0) >= thr:
                out.append(sym)
        return out

    def close(self) -> None:
        if self._client is not None:
            try:
                self._loop.run(self._client.close(), timeout=10)
            except Exception:
                pass
        self._loop.stop()
        self._connected = False
