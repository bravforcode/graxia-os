"""Tests for market_data/tick_recorder.py — new delta-stream fields
(time_msc, volume, mt5_flags) must pass through record_tick while legacy
calls keep working with None defaults."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from market_data.tick_recorder import TickRecorder


def test_record_tick_carries_new_fields():
    rec = TickRecorder("XAUUSD", "s1").record_tick(
        bid=Decimal("2300.00"),
        ask=Decimal("2300.20"),
        last=Decimal("2300.10"),
        timestamp_utc=datetime.now(UTC),
        time_msc=1764864000000,
        volume=1.5,
        mt5_flags=2,
    )
    assert rec.time_msc == 1764864000000
    assert rec.volume == 1.5
    assert rec.mt5_flags == 2
    assert rec.flags == ""  # quality-tag string untouched


def test_record_tick_defaults_legacy_fields_none():
    rec = TickRecorder("XAUUSD", "s1").record_tick(
        bid=Decimal("1"),
        ask=Decimal("2"),
        last=Decimal("1.5"),
        timestamp_utc=datetime.now(UTC),
    )
    assert rec.time_msc is None
    assert rec.volume is None
    assert rec.mt5_flags is None
