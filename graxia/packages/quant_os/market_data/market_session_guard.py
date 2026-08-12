"""
Market Session Guard for Quant OS

Determines if the market is currently open for a given symbol.
Accounts for weekend closures and configurable session windows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from enum import Enum


class SessionState(str, Enum):
    """Market session state."""

    OPEN = "OPEN"
    CLOSED_WEEKEND = "CLOSED_WEEKEND"
    CLOSED_HOLIDAY = "CLOSED_HOLIDAY"
    CLOSED_SESSION = "CLOSED_SESSION"
    UNKNOWN = "UNKNOWN"


@dataclass
class SessionResult:
    """Result of a session check."""

    state: SessionState
    symbol: str
    check_time_utc: datetime
    reason: str
    next_open_utc: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.state == SessionState.OPEN

    @property
    def is_eligible_for_order(self) -> bool:
        return self.state == SessionState.OPEN

    def summary(self) -> str:
        return f"Session {self.state.value}: {self.reason}"


@dataclass
class MarketSessionConfig:
    """Configuration for market session hours."""

    # Forex sessions (UTC times)
    forex_open_utc: time = time(0, 0)  # Sunday 22:00 EST = 00:00 UTC Monday
    forex_close_utc: time = time(22, 0)  # Friday 17:00 EST = 22:00 UTC

    # Weekend detection
    weekend_days: tuple[int, int] = (5, 6)  # Saturday=5, Sunday=6

    # Holiday dates (month, day) - simplified
    holidays: tuple[tuple[int, int], ...] = (
        (1, 1),  # New Year's Day
        (7, 4),  # Independence Day (US)
        (12, 25),  # Christmas
    )


class MarketSessionGuard:
    """
    Determines if the market is open for a given symbol.

    Checks:
    1. Weekend closure (Saturday/Sunday)
    2. Holiday closure
    3. Session hours (configurable)

    Fails closed: any error returns CLOSED state.
    """

    def __init__(
        self,
        symbol: str,
        config: MarketSessionConfig | None = None,
    ):
        self._symbol = symbol
        self._config = config or MarketSessionConfig()

    def check(self, now_utc: datetime | None = None) -> SessionResult:
        """
        Check if the market is currently open.

        Args:
            now_utc: Current time in UTC. If None, uses system time.

        Returns:
            SessionResult with open/closed state and reason.
        """
        try:
            check_time = now_utc or datetime.now(UTC)
            if check_time.tzinfo is None:
                check_time = check_time.replace(tzinfo=UTC)

            # 1. Check weekend
            if check_time.weekday() in self._config.weekend_days:
                return SessionResult(
                    state=SessionState.CLOSED_WEEKEND,
                    symbol=self._symbol,
                    check_time_utc=check_time,
                    reason=f"Market closed: weekend (day={check_time.weekday()})",
                )

            # 2. Check holiday
            month_day = (check_time.month, check_time.day)
            if month_day in self._config.holidays:
                return SessionResult(
                    state=SessionState.CLOSED_HOLIDAY,
                    symbol=self._symbol,
                    check_time_utc=check_time,
                    reason=f"Market closed: holiday ({check_time.strftime('%Y-%m-%d')})",
                )

            # 3. Check session hours
            current_time = check_time.time()
            if not (self._config.forex_open_utc <= current_time < self._config.forex_close_utc):
                return SessionResult(
                    state=SessionState.CLOSED_SESSION,
                    symbol=self._symbol,
                    check_time_utc=check_time,
                    reason=(
                        f"Market closed: outside session hours "
                        f"({self._config.forex_open_utc}-{self._config.forex_close_utc} UTC)"
                    ),
                )

            return SessionResult(
                state=SessionState.OPEN,
                symbol=self._symbol,
                check_time_utc=check_time,
                reason="Market is open",
            )

        except Exception as e:
            # Fails closed
            return SessionResult(
                state=SessionState.CLOSED_SESSION,
                symbol=self._symbol,
                check_time_utc=datetime.now(UTC),
                reason=f"Session check failed: {e} (fails closed)",
            )

    def is_open(self, now_utc: datetime | None = None) -> bool:
        """Simple boolean check: is the market open?"""
        return self.check(now_utc).is_open
