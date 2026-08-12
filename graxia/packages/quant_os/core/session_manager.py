"""Session manager for asset-class trading hours and tradeability checks."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AssetClass(str, Enum):
    """Asset class classification."""
    METALS = "metals"
    FOREX = "forex"
    CRYPTO = "crypto"
    INDICES = "indices"


@dataclass(frozen=True)
class SessionWindow:
    """Defines a trading session open/close in UTC."""
    open_time: dt.time
    close_time: dt.time


@dataclass(frozen=True)
class SessionDefinition:
    """Complete session definition for an instrument or asset class."""
    asset_class: AssetClass
    schedule_type: str  # "weekday_24h", "always_open", "custom"
    windows: list[SessionWindow]
    close_day: Optional[str] = None       # e.g. "friday"
    close_time: Optional[dt.time] = None  # UTC close time on close_day
    high_impact_hours: Optional[list[SessionWindow]] = None


# ---------------------------------------------------------------------------
# Session definitions per asset class
# ---------------------------------------------------------------------------

_METALS_SESSION = SessionDefinition(
    asset_class=AssetClass.METALS,
    schedule_type="weekday_24h",
    windows=[SessionWindow(open_time=dt.time(0, 0), close_time=dt.time(23, 59, 59))],
    close_day="friday",
    close_time=dt.time(22, 0),
    high_impact_hours=[
        SessionWindow(open_time=dt.time(12, 30), close_time=dt.time(14, 0)),
    ],
)

_FOREX_SESSION = SessionDefinition(
    asset_class=AssetClass.FOREX,
    schedule_type="weekday_24h",
    windows=[SessionWindow(open_time=dt.time(0, 0), close_time=dt.time(23, 59, 59))],
    close_day="friday",
    close_time=dt.time(22, 0),
    high_impact_hours=[
        SessionWindow(open_time=dt.time(12, 30), close_time=dt.time(14, 0)),
    ],
)

_CRYPTO_SESSION = SessionDefinition(
    asset_class=AssetClass.CRYPTO,
    schedule_type="always_open",
    windows=[SessionWindow(open_time=dt.time(0, 0), close_time=dt.time(23, 59, 59))],
    close_day=None,
    close_time=None,
    high_impact_hours=None,
)

_INDEX_SESSIONS: dict[str, SessionDefinition] = {
    "US30": SessionDefinition(
        asset_class=AssetClass.INDICES,
        schedule_type="custom",
        windows=[SessionWindow(open_time=dt.time(13, 30), close_time=dt.time(20, 0))],
        close_day=None,
        close_time=None,
        high_impact_hours=[
            SessionWindow(open_time=dt.time(13, 30), close_time=dt.time(14, 30)),
        ],
    ),
    "NAS100": SessionDefinition(
        asset_class=AssetClass.INDICES,
        schedule_type="custom",
        windows=[SessionWindow(open_time=dt.time(13, 30), close_time=dt.time(20, 0))],
        close_day=None,
        close_time=None,
        high_impact_hours=[
            SessionWindow(open_time=dt.time(13, 30), close_time=dt.time(14, 30)),
        ],
    ),
    "UK100": SessionDefinition(
        asset_class=AssetClass.INDICES,
        schedule_type="custom",
        windows=[SessionWindow(open_time=dt.time(8, 0), close_time=dt.time(16, 30))],
        close_day=None,
        close_time=None,
        high_impact_hours=[
            SessionWindow(open_time=dt.time(8, 0), close_time=dt.time(9, 0)),
        ],
    ),
    "GER40": SessionDefinition(
        asset_class=AssetClass.INDICES,
        schedule_type="custom",
        windows=[SessionWindow(open_time=dt.time(7, 0), close_time=dt.time(15, 30))],
        close_day=None,
        close_time=None,
        high_impact_hours=[
            SessionWindow(open_time=dt.time(7, 0), close_time=dt.time(8, 0)),
        ],
    ),
}

# Canonical registry
SESSIONS: dict[str, SessionDefinition] = {
    # Metals
    "XAUUSD": _METALS_SESSION,
    "XAGUSD": _METALS_SESSION,
    # Forex majors
    "EURUSD": _FOREX_SESSION,
    "GBPUSD": _FOREX_SESSION,
    "USDJPY": _FOREX_SESSION,
    "AUDUSD": _FOREX_SESSION,
    "USDCAD": _FOREX_SESSION,
    "USDCHF": _FOREX_SESSION,
    "NZDUSD": _FOREX_SESSION,
    # Crypto
    "BTCUSD": _CRYPTO_SESSION,
    "ETHUSD": _CRYPTO_SESSION,
    # Indices
    **_INDEX_SESSIONS,
}


class SessionManager:
    """Checks tradeability, time-to-open, and high-impact windows for instruments.

    All times are compared in UTC.
    """

    def __init__(self, sessions: dict[str, SessionDefinition] | None = None) -> None:
        self._sessions = sessions or SESSIONS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_tradeable(self, symbol: str, now: dt.datetime | None = None) -> bool:
        """Return True if *symbol* is currently within its trading session.

        Parameters
        ----------
        symbol:
            Instrument symbol (e.g. ``"XAUUSD"``).
        now:
            Current UTC datetime.  Defaults to ``datetime.now(timezone.utc)``.
        """
        session = self._resolve(symbol)
        if session is None:
            return False

        utc_now = now or dt.datetime.now(dt.UTC)
        utc_time = utc_now.time()
        weekday = utc_now.weekday()  # 0=Mon … 6=Sun

        # Always-open assets (crypto)
        if session.schedule_type == "always_open":
            return True

        # Weekday 24h assets (metals, forex) — closed Sat & before Friday close
        if session.schedule_type == "weekday_24h":
            if weekday >= 5:  # Saturday / Sunday
                return False
            if weekday == 4 and session.close_time and utc_time >= session.close_time:
                return False
            return True

        # Custom window assets (indices)
        if session.schedule_type == "custom":
            if weekday >= 5:
                return False
            return any(w.open_time <= utc_time <= w.close_time for w in session.windows)

        return False

    def minutes_to_open(self, symbol: str, now: dt.datetime | None = None) -> float:
        """Return minutes until the next session open for *symbol*.

        Returns ``0.0`` if the session is currently open.
        Returns ``-1.0`` if the symbol is unknown.
        """
        session = self._resolve(symbol)
        if session is None:
            return -1.0

        utc_now = now or dt.datetime.now(dt.UTC)

        if self.is_tradeable(symbol, utc_now):
            return 0.0

        # Find next open
        if session.schedule_type == "always_open":
            return 0.0

        if session.schedule_type == "weekday_24h":
            return self._minutes_to_weekday_open(utc_now, session)

        if session.schedule_type == "custom":
            return self._minutes_to_custom_open(utc_now, session)

        return -1.0

    def is_high_impact_window(self, symbol: str, now: dt.datetime | None = None) -> bool:
        """Return True if *symbol* is in a high-impact news/liquidity window.

        Parameters
        ----------
        symbol:
            Instrument symbol.
        now:
            Current UTC datetime.
        """
        session = self._resolve(symbol)
        if session is None or session.high_impact_hours is None:
            return False

        utc_now = now or dt.datetime.now(dt.UTC)
        utc_time = utc_now.time()

        return any(w.open_time <= utc_time <= w.close_time for w in session.high_impact_hours)

    def get_session_info(self, symbol: str) -> dict[str, object]:
        """Return a JSON-serialisable dict describing the session for *symbol*."""
        session = self._resolve(symbol)
        if session is None:
            return {"symbol": symbol, "error": "unknown_symbol"}

        utc_now = dt.datetime.now(dt.UTC)
        return {
            "symbol": symbol,
            "asset_class": session.asset_class.value,
            "schedule_type": session.schedule_type,
            "is_tradeable": self.is_tradeable(symbol, utc_now),
            "minutes_to_open": self.minutes_to_open(symbol, utc_now),
            "is_high_impact_window": self.is_high_impact_window(symbol, utc_now),
            "windows": [
                {"open": w.open_time.isoformat(), "close": w.close_time.isoformat()}
                for w in session.windows
            ],
            "close_day": session.close_day,
            "close_time": session.close_time.isoformat() if session.close_time else None,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, symbol: str) -> SessionDefinition | None:
        """Look up session definition by symbol (case-insensitive)."""
        return self._sessions.get(symbol.upper())

    @staticmethod
    def _minutes_between(a: dt.datetime, b: dt.datetime) -> float:
        """Absolute minutes between two datetimes."""
        return abs((b - a).total_seconds()) / 60.0

    def _minutes_to_weekday_open(
        self, utc_now: dt.datetime, session: SessionDefinition
    ) -> float:
        """Minutes until the next weekday-24h session opens."""
        candidate = utc_now
        for _ in range(8):  # max 7-day lookahead
            candidate += dt.timedelta(days=1)
            candidate = candidate.replace(hour=0, minute=0, second=0, microsecond=0)
            if candidate.weekday() < 5:
                return self._minutes_between(utc_now, candidate)
        return -1.0

    def _minutes_to_custom_open(
        self, utc_now: dt.datetime, session: SessionDefinition
    ) -> float:
        """Minutes until the next custom-window session opens."""
        utc_time = utc_now.time()
        weekday = utc_now.weekday()

        # Check remaining windows today
        if weekday < 5:
            for w in session.windows:
                if utc_time < w.open_time:
                    target = utc_now.replace(
                        hour=w.open_time.hour,
                        minute=w.open_time.minute,
                        second=0,
                        microsecond=0,
                    )
                    return self._minutes_between(utc_now, target)

        # Next weekday
        candidate = utc_now
        for _ in range(8):
            candidate += dt.timedelta(days=1)
            candidate = candidate.replace(
                hour=session.windows[0].open_time.hour,
                minute=session.windows[0].open_time.minute,
                second=0,
                microsecond=0,
            )
            if candidate.weekday() < 5:
                return self._minutes_between(utc_now, candidate)

        return -1.0
