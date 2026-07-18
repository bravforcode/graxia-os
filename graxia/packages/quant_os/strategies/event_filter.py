"""
Event Filter — FOMC/CPI date management for strategy exclusion windows.

Provides:
- Hardcoded FOMC meeting dates (2020-2026)
- CPI release dates (approximate, 8:30 AM ET on specific days)
- 48h exclusion window check

Usage:
    from strategies.event_filter import EventFilter
    ef = EventFilter()
    ef.is_excluded(datetime(2024, 3, 20, 14, 0))  # True if near FOMC
"""

from __future__ import annotations

from datetime import datetime, timedelta, UTC


# FOMC meeting dates (2-day meetings, decision on day 2 at 2:00 PM ET)
# Source: federalreserve.gov/monetarypolicy/fomccalendars.htm
FOMC_DATES = [
    # 2020
    "2020-01-29", "2020-03-03", "2020-03-15", "2020-04-29", "2020-06-10",
    "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
    # 2021
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28",
    "2021-09-22", "2021-11-03", "2021-12-15",
    # 2022
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27",
    "2022-09-21", "2022-11-02", "2022-12-14",
    # 2023
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26",
    "2023-09-20", "2023-11-01", "2023-12-13",
    # 2024
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31",
    "2024-09-18", "2024-11-07", "2024-12-18",
    # 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30",
    "2025-09-17", "2025-10-29", "2025-12-17",
    # 2026
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
    "2026-09-16", "2026-10-28", "2026-12-16",
]

# CPI release dates (approximate — 8:30 AM ET on specific days)
# Usually 2nd or 3rd Wednesday/Thursday of the month
CPI_DATES = [
    # 2020
    "2020-01-14", "2020-02-13", "2020-03-11", "2020-04-10", "2020-05-12",
    "2020-06-10", "2020-07-14", "2020-08-12", "2020-09-11", "2020-10-13",
    "2020-11-12", "2020-12-10",
    # 2021
    "2021-01-13", "2021-02-10", "2021-03-10", "2021-04-13", "2021-05-12",
    "2021-06-10", "2021-07-13", "2021-08-11", "2021-09-14", "2021-10-13",
    "2021-11-10", "2021-12-10",
    # 2022
    "2022-01-12", "2022-02-10", "2022-03-10", "2022-04-12", "2022-05-11",
    "2022-06-10", "2022-07-13", "2022-08-10", "2022-09-13", "2022-10-13",
    "2022-11-10", "2022-12-13",
    # 2023
    "2023-01-12", "2023-02-14", "2023-03-14", "2023-04-12", "2023-05-10",
    "2023-06-13", "2023-07-12", "2023-08-10", "2023-09-13", "2023-10-12",
    "2023-11-14", "2023-12-12",
    # 2024
    "2024-01-11", "2024-02-13", "2024-03-12", "2024-04-10", "2024-05-15",
    "2024-06-12", "2024-07-11", "2024-08-14", "2024-09-11", "2024-10-10",
    "2024-11-13", "2024-12-11",
    # 2025
    "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10", "2025-05-13",
    "2025-06-11", "2025-07-15", "2025-08-12", "2025-09-10", "2025-10-14",
    "2025-11-12", "2025-12-10",
    # 2026
    "2026-01-14", "2026-02-11", "2026-03-11", "2026-04-14", "2026-05-13",
    "2026-06-10", "2026-07-14", "2026-08-12", "2026-09-10", "2026-10-14",
    "2026-11-10", "2026-12-10",
]


class EventFilter:
    """Filter trades around high-impact economic events.

    Default exclusion window: 48 hours before and after event.
    """

    def __init__(self, exclusion_hours: int = 48):
        self.exclusion_hours = exclusion_hours
        self._event_datetimes: list[datetime] = []

        # Parse all event dates
        for date_str in FOMC_DATES + CPI_DATES:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
                self._event_datetimes.append(dt)
            except ValueError:
                continue

        # Sort for efficient lookup
        self._event_datetimes.sort()

    def is_excluded(self, dt: datetime) -> bool:
        """Check if datetime falls within exclusion window of any event."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        window = timedelta(hours=self.exclusion_hours)

        for event_dt in self._event_datetimes:
            if abs((dt - event_dt).total_seconds()) < window.total_seconds():
                return True

        return False

    def get_exclusion_reason(self, dt: datetime) -> str | None:
        """Return event type that causes exclusion, or None."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        window = timedelta(hours=self.exclusion_hours)

        for event_dt in self._event_datetimes:
            if abs((dt - event_dt).total_seconds()) < window.total_seconds():
                hours_away = abs((dt - event_dt).total_seconds()) / 3600
                # Determine event type
                date_str = event_dt.strftime("%Y-%m-%d")
                if date_str in FOMC_DATES:
                    return f"FOMC ({date_str}, {hours_away:.1f}h away)"
                else:
                    return f"CPI ({date_str}, {hours_away:.1f}h away)"

        return None

    def get_upcoming_events(self, dt: datetime, lookahead_days: int = 7) -> list[dict]:
        """Return list of upcoming events within lookahead window."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        window = timedelta(days=lookahead_days)
        upcoming = []

        for event_dt in self._event_datetimes:
            if event_dt > dt and (event_dt - dt) < window:
                date_str = event_dt.strftime("%Y-%m-%d")
                event_type = "FOMC" if date_str in FOMC_DATES else "CPI"
                upcoming.append({
                    "date": event_dt,
                    "type": event_type,
                    "hours_away": (event_dt - dt).total_seconds() / 3600,
                })

        return upcoming

    @property
    def total_events(self) -> int:
        """Total number of loaded events."""
        return len(self._event_datetimes)

    @property
    def date_range(self) -> tuple[str, str]:
        """Date range of loaded events."""
        if not self._event_datetimes:
            return ("", "")
        return (
            self._event_datetimes[0].strftime("%Y-%m-%d"),
            self._event_datetimes[-1].strftime("%Y-%m-%d"),
        )
