"""Test canonical UTC tick authority. No MT5 dependency for unit tests."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shadow.canonical_tick_authority import (
    query_canonical_utc_tick, check_native_quote_divergence,
    is_time_authority_consistent, is_time_authority_blocking,
    TIME_SOURCE_CONSISTENT, TIME_SOURCE_INCONSISTENT,
    CANONICAL_TICK_STALE, CANONICAL_TICK_MISSING,
    CANONICAL_TICK_OUTSIDE_WINDOW, CANONICAL_TICK_FUTURE,
    CANONICAL_TICK_INVALID_PRICE,
)


class FakeTick:
    """Simulate a copy_ticks_range tick tuple."""
    def __getitem__(self, idx):
        return self._data[idx]

    def __init__(self, time_sec, bid, ask, last=0, volume=100, flags=0, time_msc=0):
        self._data = (time_sec, time_msc, bid, ask, last, volume, flags)

    def __len__(self): return len(self._data)
    def __iter__(self): return iter(self._data)


class TestCanonicalTickQuery:
    def test_no_mt5_returns_inconsistent(self):
        ev = query_canonical_utc_tick(None, "XAUUSD")
        assert ev.time_authority_status == TIME_SOURCE_INCONSISTENT

    def test_no_ticks_returns_missing(self):
        mt5 = MagicMock()
        mt5.copy_ticks_range.return_value = None
        ev = query_canonical_utc_tick(mt5, "XAUUSD")
        assert ev.time_authority_status == CANONICAL_TICK_MISSING

    def test_empty_ticks_returns_missing(self):
        mt5 = MagicMock()
        mt5.copy_ticks_range.return_value = []
        ev = query_canonical_utc_tick(mt5, "XAUUSD")
        assert ev.time_authority_status == CANONICAL_TICK_MISSING

    def test_fresh_tick_in_window_consistent(self):
        mt5 = MagicMock()
        now = datetime.now(timezone.utc)
        tick_time = now.timestamp() - 1  # 1 second ago
        mt5.copy_ticks_range.return_value = [FakeTick(tick_time, 4120.0, 4120.18)]
        ev = query_canonical_utc_tick(mt5, "XAUUSD")
        assert ev.time_authority_status == TIME_SOURCE_CONSISTENT
        assert ev.canonical_bid == 4120.0
        assert ev.canonical_ask == 4120.18

    def test_tick_outside_window(self):
        mt5 = MagicMock()
        now = datetime.now(timezone.utc)
        tick_time = (now - timedelta(hours=2)).timestamp()  # 2 hours ago
        mt5.copy_ticks_range.return_value = [FakeTick(tick_time, 4120.0, 4120.18)]
        ev = query_canonical_utc_tick(mt5, "XAUUSD")
        assert ev.time_authority_status == CANONICAL_TICK_OUTSIDE_WINDOW

    def test_future_tick(self):
        mt5 = MagicMock()
        now = datetime.now(timezone.utc)
        tick_time = (now + timedelta(hours=3)).timestamp()  # 3 hours in future
        mt5.copy_ticks_range.return_value = [FakeTick(tick_time, 4120.0, 4120.18)]
        ev = query_canonical_utc_tick(mt5, "XAUUSD")
        assert ev.time_authority_status == CANONICAL_TICK_FUTURE

    def test_stale_tick(self):
        mt5 = MagicMock()
        now = datetime.now(timezone.utc)
        tick_time = (now - timedelta(seconds=30)).timestamp()  # 30s old
        mt5.copy_ticks_range.return_value = [FakeTick(tick_time, 4120.0, 4120.18)]
        ev = query_canonical_utc_tick(mt5, "XAUUSD")
        assert ev.time_authority_status == CANONICAL_TICK_STALE

    def test_invalid_price_ask_below_bid(self):
        mt5 = MagicMock()
        now = datetime.now(timezone.utc)
        tick_time = now.timestamp() - 1
        mt5.copy_ticks_range.return_value = [FakeTick(tick_time, 4120.18, 4120.0)]
        ev = query_canonical_utc_tick(mt5, "XAUUSD")
        assert ev.time_authority_status == CANONICAL_TICK_INVALID_PRICE


class TestNativeQuoteDivergence:
    def test_prices_match(self):
        ev = type('obj', (object,), {'canonical_bid': 4120.0, 'canonical_ask': 4120.18})()
        check_native_quote_divergence(ev, 4120.0, 4120.18, 0.01, 5)
        assert ev.quote_price_divergence_passed
        assert ev.quote_price_divergence_ticks == 0

    def test_prices_diverge_beyond_tolerance(self):
        ev = type('obj', (object,), {'canonical_bid': 4120.0, 'canonical_ask': 4120.18})()
        check_native_quote_divergence(ev, 4120.50, 4120.68, 0.01, 5)
        assert not ev.quote_price_divergence_passed
        assert ev.quote_price_divergence_ticks >= 50

    def test_prices_within_tolerance(self):
        ev = type('obj', (object,), {'canonical_bid': 4120.0, 'canonical_ask': 4120.18})()
        check_native_quote_divergence(ev, 4120.02, 4120.20, 0.01, 5)
        assert ev.quote_price_divergence_passed

    def test_missing_native_quote(self):
        ev = type('obj', (object,), {'canonical_bid': 4120.0, 'canonical_ask': 4120.18})()
        check_native_quote_divergence(ev, None, None, 0.01, 5)
        assert not ev.quote_price_divergence_passed


class TestAuthorityStatusHelpers:
    def test_consistent_allows(self):
        assert is_time_authority_consistent(TIME_SOURCE_CONSISTENT)
        assert not is_time_authority_blocking(TIME_SOURCE_CONSISTENT)

    def test_inconsistent_blocks(self):
        for status in [TIME_SOURCE_INCONSISTENT, CANONICAL_TICK_STALE,
                       CANONICAL_TICK_MISSING, CANONICAL_TICK_FUTURE,
                       CANONICAL_TICK_OUTSIDE_WINDOW, CANONICAL_TICK_INVALID_PRICE]:
            assert not is_time_authority_consistent(status)
            assert is_time_authority_blocking(status)


class TestUTCAwareDatetime:
    def test_query_uses_utc_aware_datetimes(self):
        """copy_ticks_range must receive timezone-aware UTC datetimes."""
        from datetime import datetime, timezone
        mt5 = MagicMock()
        now = datetime.now(timezone.utc)
        tick_time = now.timestamp() - 1
        mt5.copy_ticks_range.return_value = [FakeTick(tick_time, 4120.0, 4120.18)]

        ev = query_canonical_utc_tick(mt5, "XAUUSD")

        # Verify the query was called with UTC-aware datetimes
        call_args = mt5.copy_ticks_range.call_args
        assert call_args is not None
        from_dt = call_args[0][1]
        to_dt = call_args[0][2]
        assert from_dt.tzinfo is not None
        assert to_dt.tzinfo is not None
        assert ev.time_authority_status == TIME_SOURCE_CONSISTENT

    def test_canonical_tick_time_is_utc_isoformat(self):
        mt5 = MagicMock()
        now = datetime.now(timezone.utc)
        tick_time = now.timestamp() - 1
        mt5.copy_ticks_range.return_value = [FakeTick(tick_time, 4120.0, 4120.18)]
        ev = query_canonical_utc_tick(mt5, "XAUUSD")
        assert ev.canonical_tick_time_utc is not None
        # Verify it parses as UTC
        parsed = datetime.fromisoformat(ev.canonical_tick_time_utc)
        assert parsed.tzinfo is not None or 'Z' in ev.canonical_tick_time_utc
