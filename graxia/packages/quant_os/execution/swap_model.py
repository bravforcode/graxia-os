"""Swap model — explicit cost for overnight D1 strategies."""

# ponytail: explicit swap model for overnight D1 strategies

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum


class SwapMode(Enum):
    NONE = "none"
    FIXED = "fixed"
    HISTORICAL = "historical"


@dataclass(frozen=True)
class SwapRates:
    swap_long: Decimal = Decimal("0")
    swap_short: Decimal = Decimal("0")
    rollover_day: int = 3
    mode: SwapMode = SwapMode.NONE


@dataclass(frozen=True)
class SwapResult:
    swap_applied: Decimal
    swap_mode: SwapMode
    days_held: int
    rollover_events: int
    is_unknown: bool


def calculate_swap(
    entry_time: datetime,
    exit_time: datetime,
    side: str,
    volume: Decimal,
    swap_rates: SwapRates,
) -> SwapResult:
    if swap_rates.mode == SwapMode.NONE:
        days = (exit_time.date() - entry_time.date()).days
        return SwapResult(
            swap_applied=Decimal("0"),
            swap_mode=SwapMode.NONE,
            days_held=days,
            rollover_events=0,
            is_unknown=days > 0,
        )

    daily_rate = swap_rates.swap_long if side == "BUY" else swap_rates.swap_short
    current = entry_time.date() + timedelta(days=1)
    end = exit_time.date()

    days = 0
    wed_count = 0
    while current <= end:
        days += 1
        if current.weekday() == swap_rates.rollover_day:
            wed_count += 1
        current += timedelta(days=1)

    other_count = days - wed_count
    effective = wed_count * 3 + other_count
    total = daily_rate * volume * effective

    return SwapResult(
        swap_applied=total,
        swap_mode=swap_rates.mode,
        days_held=days,
        rollover_events=days,
        is_unknown=False,
    )


class SwapPolicy:
    def __init__(self, swap_rates: SwapRates) -> None:
        self._rates = swap_rates

    def apply(
        self,
        entry_time: datetime,
        exit_time: datetime,
        side: str,
        volume: Decimal,
    ) -> SwapResult:
        return calculate_swap(entry_time, exit_time, side, volume, self._rates)
