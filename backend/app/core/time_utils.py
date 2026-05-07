from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

BUSINESS_TIMEZONE = ZoneInfo("Asia/Bangkok")


def business_now() -> datetime:
    return datetime.now(BUSINESS_TIMEZONE)


def business_today() -> date:
    return business_now().date()


def business_day_bounds_utc(target_date: date | None = None) -> tuple[datetime, datetime]:
    selected_date = target_date or business_today()
    start_local = datetime.combine(selected_date, time.min, tzinfo=BUSINESS_TIMEZONE)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)
