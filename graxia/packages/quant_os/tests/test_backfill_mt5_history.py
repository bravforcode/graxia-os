"""Tests for Task 12 — MT5 history backfill worker (get_ticks_range
gateway wrapper + per-UTC-day parquet grouping, idempotent)."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from broker.mt5_gateway import get_ticks_range
from data_pipeline.backfill import mt5_history


def _fake_mt5():
    class FakeMT5:
        COPY_TICKS_ALL = 2

        def copy_ticks_range(self, symbol, from_msc, to_msc, count, flags):
            assert count == 100000 and flags == 2
            return None  # terminal has no history — treat as empty

    return FakeMT5()


def test_get_ticks_range_empty(monkeypatch):
    monkeypatch.setattr("broker.mt5_gateway._get_mt5", lambda: _fake_mt5())
    assert get_ticks_range("XAUUSD", 0, 1) == []


def test_fetch_ticks_groups_by_utc_day_and_is_idempotent(tmp_path, monkeypatch):
    day1_msc = int(datetime(2026, 8, 4, 0, 0, tzinfo=UTC).timestamp() * 1000)
    day2_msc = int(datetime(2026, 8, 5, 0, 0, tzinfo=UTC).timestamp() * 1000)
    served = {"n": 0}

    def fake_range(symbol, from_msc, to_msc, count=100000, flags=None):
        if served["n"] == 0:
            served["n"] += 1
            return [{"time_msc": day1_msc + 1000, "bid": 1.0, "ask": 1.1, "last": 1.05, "volume": 1.0, "flags": 0}]
        return [{"time_msc": day2_msc + 1000, "bid": 1.2, "ask": 1.3, "last": 1.25, "volume": 2.0, "flags": 0}]

    monkeypatch.setattr(mt5_history, "_get_ticks_range", fake_range)
    paths = mt5_history.fetch_ticks("XAUUSD", day1_msc, day2_msc, tmp_path)
    assert len(paths) == 2
    assert pd.read_parquet(paths[0]).iloc[0]["source"] == "mt5_history"
    # idempotent: same call, no new files
    assert mt5_history.fetch_ticks("XAUUSD", day1_msc, day2_msc, tmp_path) == []
