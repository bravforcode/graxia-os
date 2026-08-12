"""Market Session Guard — blocks orders outside trading hours or during low-liquidity windows.

Checks MT5 symbol info for trading sessions and skips trades when:
  1. Market is closed (holiday / non-trading day)
  2. Within the first or last N minutes of a session (low-liquidity bookends)
  3. During the daily rollover window (typically 21:55–22:16 UTC)

Usage::

    from risk.market_session_guard import MarketSessionGuard

    guard = MarketSessionGuard()
    result = guard.check("XAUUSD")
    if not result.allowed:
        print(f"Skipped: {result.reason}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any, Protocol

from ..core.symbol_registry import symbol_to_asset_class as _symbol_to_asset_class

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default session boundaries (UTC) — used when MT5 info unavailable
# ---------------------------------------------------------------------------

# Major sessions by asset class (UTC hours)
_DEFAULT_SESSIONS: dict[str, list[tuple[time, time]]] = {
    "metals": [
        (time(1, 0), time(21, 55)),  # Nearly 24h via Comex + spot
    ],
    "forex": [
        (time(1, 0), time(21, 55)),  # Spot FX: Sun 22 UTC → Fri 22 UTC
    ],
    "crypto": [],  # 24/7 — no session restriction
    "indices": [
        (time(13, 0), time(21, 0)),  # US indices via CFD
    ],
}

# Rollover window (UTC) — all instruments
_ROLLOVER_START = time(21, 55)
_ROLLOVER_END = time(22, 16)

# Low-liquidity bookends (minutes from session open/close to avoid)
_DEFAULT_BUFFER_MINUTES = 5


# ---------------------------------------------------------------------------
# Symbol → asset class mapping — imported from core.symbol_registry
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# MT5 interface protocol (duck-typed)
# ---------------------------------------------------------------------------


class MT5Like(Protocol):
    """Minimal MT5 interface needed by MarketSessionGuard."""

    def symbol_info(self, symbol: str) -> Any: ...


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionCheckResult:
    """Outcome of a market session check."""

    allowed: bool
    reason: str = ""
    session: str = ""
    market_open: bool = True
    in_buffer: bool = False
    in_rollover: bool = False


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


class MarketSessionGuard:
    """Check whether a symbol's market is open and not in a low-liquidity window.

    Parameters:
        mt5: Optional MT5 instance for live symbol_info queries.
        buffer_minutes: Minutes from session open/close to treat as low-liquidity
                        (default 5).
        check_holidays: Whether to reject orders on known holidays (uses MT5
                        symbol_info().trade_mode if available).
    """

    def __init__(
        self,
        mt5: MT5Like | None = None,
        buffer_minutes: int = _DEFAULT_BUFFER_MINUTES,
        check_holidays: bool = True,
    ) -> None:
        self._mt5 = mt5
        self._buffer_minutes = buffer_minutes
        self._check_holidays = check_holidays

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        symbol: str,
        now: datetime | None = None,
    ) -> SessionCheckResult:
        """Run all session checks for *symbol* at *now* (UTC).

        Returns ``SessionCheckResult(allowed=True)`` when safe to trade,
        or ``SessionCheckResult(allowed=False, reason=...)`` when blocked.
        """
        now = now or datetime.now(UTC)
        now_utc = now.astimezone(UTC)

        asset_class = _symbol_to_asset_class(symbol)

        # --- 1. Crypto: 24/7, always allowed (skip session checks) ---
        if asset_class == "crypto":
            rollover = self._in_rollover(now_utc)
            if rollover:
                return SessionCheckResult(
                    allowed=False,
                    reason=f"Crypto in rollover window ({_ROLLOVER_START}–{_ROLLOVER_END} UTC)",
                    session="rollover",
                    market_open=True,
                    in_rollover=True,
                )
            return SessionCheckResult(allowed=True, session="24/7", market_open=True)

        # --- 2. MT5 trade_mode check (holidays, maintenance) ---
        if self._mt5 is not None and self._check_holidays:
            mt5_check = self._check_mt5_trade_mode(symbol)
            if mt5_check is not None:
                return mt5_check

        # --- 3. Rollover window ---
        if self._in_rollover(now_utc):
            return SessionCheckResult(
                allowed=False,
                reason=f"In rollover window ({_ROLLOVER_START}–{_ROLLOVER_END} UTC)",
                session="rollover",
                market_open=True,
                in_rollover=True,
            )

        # --- 4. Session bounds ---
        sessions = _DEFAULT_SESSIONS.get(asset_class, _DEFAULT_SESSIONS["forex"])
        in_session, session_name = self._in_session(now_utc, sessions)

        if not in_session:
            return SessionCheckResult(
                allowed=False,
                reason=f"Outside trading session ({session_name}) for {asset_class}",
                session=session_name,
                market_open=False,
            )

        # --- 5. Buffer check (low-liquidity bookends) ---
        in_buffer, buffer_reason = self._in_buffer(now_utc, sessions)
        if in_buffer:
            return SessionCheckResult(
                allowed=False,
                reason=buffer_reason,
                session=session_name,
                market_open=True,
                in_buffer=True,
            )

        return SessionCheckResult(allowed=True, session=session_name, market_open=True)

    def should_skip(
        self,
        symbol: str,
        now: datetime | None = None,
    ) -> tuple[bool, str]:
        """Convenience: returns ``(should_skip, reason)`` for logging."""
        result = self.check(symbol, now)
        return (not result.allowed, result.reason)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_mt5_trade_mode(self, symbol: str) -> SessionCheckResult | None:
        """Query MT5 symbol_info for trade_mode. Returns None if info unavailable."""
        try:
            info = self._mt5.symbol_info(symbol)  # type: ignore[union-attr]
            if info is None:
                return None

            # MT5 symbol_info.trade_mode values:
            #   0 = SYMBOL_TRADE_MODE_DISABLED
            #   1 = SYMBOL_TRADE_MODE_LONGONLY
            #   2 = SYMBOL_TRADE_MODE_SHORTONLY
            #   3 = SYMBOL_TRADE_MODE_CLOSEONLY
            #   4 = SYMBOL_TRADE_MODE_FULL
            trade_mode = getattr(info, "trade_mode", 4)
            if trade_mode == 0:
                return SessionCheckResult(
                    allowed=False,
                    reason="MT5 reports symbol DISABLED (trade_mode=0)",
                    session="disabled",
                    market_open=False,
                )
            if trade_mode in (1, 2):
                return SessionCheckResult(
                    allowed=False,
                    reason=f"MT5 reports restricted trading (trade_mode={trade_mode})",
                    session="restricted",
                    market_open=True,
                )

            # Check trade_is_allowed flag
            trade_allowed = getattr(info, "trade_allowed", True)
            if not trade_allowed:
                return SessionCheckResult(
                    allowed=False,
                    reason=f"MT5 reports trading not allowed for {symbol}",
                    session="blocked",
                    market_open=False,
                )

        except Exception as exc:
            logger.debug("MT5 symbol_info check failed for %s: %s", symbol, exc)

        return None

    def _in_rollover(self, now_utc: datetime) -> bool:
        """Check if current time falls in the daily rollover window."""
        t = now_utc.time()
        if _ROLLOVER_START <= _ROLLOVER_END:
            return _ROLLOVER_START <= t < _ROLLOVER_END
        # Wraps midnight (unlikely for our 21:55–22:16 window)
        return t >= _ROLLOVER_START or t < _ROLLOVER_END

    def _in_session(self, now_utc: datetime, sessions: list[tuple[time, time]]) -> tuple[bool, str]:
        """Check if now_utc falls within any of the given sessions."""
        t = now_utc.time()
        for start, end in sessions:
            name = f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')} UTC"
            if start <= end:
                if start <= t < end:
                    return True, name
            else:  # wraps midnight
                if t >= start or t < end:
                    return True, name
        return False, "closed"

    def _in_buffer(self, now_utc: datetime, sessions: list[tuple[time, time]]) -> tuple[bool, str]:
        """Check if now_utc falls within the buffer (first/last N minutes) of any session."""
        t = now_utc.time()
        buf = timedelta(minutes=self._buffer_minutes)

        for start, end in sessions:
            if start <= end:
                # Buffer at open: [start, start + buf)
                open_buf_end = (datetime.combine(now_utc.date(), start) + buf).time()
                if start <= t < open_buf_end:
                    return True, f"Within {self._buffer_minutes}min of session open ({start.strftime('%H:%M')} UTC)"

                # Buffer at close: [end - buf, end)
                close_buf_start = (datetime.combine(now_utc.date(), end) - buf).time()
                if close_buf_start <= t < end:
                    return True, f"Within {self._buffer_minutes}min of session close ({end.strftime('%H:%M')} UTC)"
            else:
                # Wraps midnight — check open buffer
                open_buf_end = (datetime.combine(now_utc.date(), start) + buf).time()
                if start <= t < open_buf_end:
                    return True, f"Within {self._buffer_minutes}min of session open ({start.strftime('%H:%M')} UTC)"

        return False, ""
