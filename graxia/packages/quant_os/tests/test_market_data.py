"""
Tests for market_data/ modules:
  feed_health, spread_monitor, market_health, clock_guard, data_watermark
"""

from datetime import datetime, timedelta, UTC
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from market_data.feed_health import FeedHealthMonitor, FeedHealthState
from market_data.spread_monitor import SpreadMonitor, SpreadState
from market_data.market_health import (
    MarketHealthMachine,
    MarketHealthState,
)
from market_data.clock_guard import ClockGuard, ClockState
from market_data.data_watermark import DataWatermarkTracker
from market_data.tick_recorder import TickRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow():
    return datetime.now(UTC)


def _make_tick_record(
    symbol="XAUUSD",
    dt=None,
    received=None,
    quality="VALID",
    seq=1,
):
    dt = dt or _utcnow()
    received = received or dt
    return TickRecord(
        timestamp_utc=dt,
        received_at_utc=received,
        symbol=symbol,
        bid=Decimal("2300.50"),
        ask=Decimal("2300.80"),
        last=Decimal("2300.65"),
        spread_points=Decimal("0.30"),
        flags="",
        sequence_id=seq,
        connection_session_id="test-session",
        source="simulated",
        data_quality=quality,
    )


# ===== feed_health tests =====


class TestFeedHealth:
    def test_feed_health_check_returns_status(self):
        monitor = FeedHealthMonitor("XAUUSD")
        now = _utcnow()
        monitor.on_tick_received(now, now)
        state = monitor.check_health()
        assert isinstance(state, FeedHealthState)
        assert state.symbol == "XAUUSD"
        assert state.state == "HEALTHY"
        assert monitor.is_healthy() is True

    def test_feed_health_stale_detects_stale(self):
        monitor = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=3.0)
        old_time = _utcnow() - timedelta(seconds=10)
        monitor.on_tick_received(old_time, old_time)
        state = monitor.check_health()
        assert state.state == "STALE_FEED"
        assert monitor.is_healthy() is False

    def test_feed_health_transitions_to_disconnected(self):
        monitor = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=1.0)
        old = _utcnow() - timedelta(seconds=5)
        monitor.on_tick_received(old, old)
        for _ in range(3):
            state = monitor.check_health()
        assert state.state == "DISCONNECTED"

    def test_feed_health_resets(self):
        monitor = FeedHealthMonitor("XAUUSD")
        monitor.on_tick_received(_utcnow(), _utcnow())
        monitor.reset()
        assert monitor.is_healthy() is False
        state = monitor.check_health()
        assert state.state == "UNKNOWN"


# ===== spread_monitor tests =====


class TestSpreadMonitor:
    def test_spread_monitor_record_records_spread(self):
        sm = SpreadMonitor("XAUUSD")
        ts = _utcnow()
        state = sm.on_tick(Decimal("2300.00"), Decimal("2300.50"), ts)
        assert isinstance(state, SpreadState)
        assert state.sample_count == 1
        assert state.current_spread_points == Decimal("0.50")

    def test_spread_monitor_alert_on_wide_spread(self):
        sm = SpreadMonitor("XAUUSD", reject_multiplier=2.0)
        ts = _utcnow()
        # Build a stable baseline with tight spreads
        for i in range(20):
            sm.on_tick(Decimal("2300.00"), Decimal("2300.20"), ts + timedelta(seconds=i))
        assert sm.is_wide_spread(Decimal("0.20")) is False
        # A spread much wider than baseline should trigger
        assert sm.is_wide_spread(Decimal("5.00")) is True

    def test_spread_monitor_baseline_updates(self):
        sm = SpreadMonitor("XAUUSD")
        ts = _utcnow()
        sm.on_tick(Decimal("100"), Decimal("101"), ts)
        sm.on_tick(Decimal("100"), Decimal("101"), ts + timedelta(seconds=1))
        mean, std = sm.get_baseline()
        assert mean == Decimal("1.00")
        assert std == Decimal("0")

    def test_spread_monitor_rejects_invalid_quotes(self):
        sm = SpreadMonitor("XAUUSD")
        ts = _utcnow()
        state = sm.on_tick(Decimal("0"), Decimal("100"), ts)
        assert state.sample_count == 0


# ===== market_health tests =====


class TestMarketHealth:
    def test_market_health_status_returns_healthy(self):
        machine = MarketHealthMachine("XAUUSD")
        feed = MagicMock(state="HEALTHY", last_tick_age_seconds=0.5, max_tick_age_seconds=3.0)
        spread = MagicMock(is_wide=False)
        clock = MagicMock(is_drifted=False)
        result = machine.evaluate(feed_health=feed, spread_state=spread, clock_state=clock)
        assert result.state == MarketHealthState.HEALTHY
        assert result.eligible_for_new_order is True
        assert result.reason_codes == []

    def test_market_health_degraded_on_disconnected(self):
        machine = MarketHealthMachine("XAUUSD")
        result = machine.evaluate(feed_health=None)
        assert result.state == MarketHealthState.DISCONNECTED
        assert result.eligible_for_new_order is False
        assert "FEED_DISCONNECTED" in result.reason_codes

    def test_market_health_degraded_on_stale(self):
        machine = MarketHealthMachine("XAUUSD")
        feed = MagicMock(state="STALE_FEED", last_tick_age_seconds=5.0, max_tick_age_seconds=3.0)
        result = machine.evaluate(feed_health=feed)
        assert result.state == MarketHealthState.STALE_FEED
        assert result.eligible_for_new_order is False

    def test_market_health_degraded_on_wide_spread(self):
        machine = MarketHealthMachine("XAUUSD")
        spread = MagicMock(is_wide=True)
        feed = MagicMock(state="HEALTHY", last_tick_age_seconds=0.5, max_tick_age_seconds=3.0)
        result = machine.evaluate(feed_health=feed, spread_state=spread)
        assert result.state == MarketHealthState.WIDE_SPREAD
        assert result.eligible_for_new_order is False

    def test_market_health_degraded_on_clock_drift(self):
        machine = MarketHealthMachine("XAUUSD")
        feed = MagicMock(state="HEALTHY", last_tick_age_seconds=0.5, max_tick_age_seconds=3.0)
        spread = MagicMock(is_wide=False)
        clock = MagicMock(is_drifted=True)
        result = machine.evaluate(feed_health=feed, spread_state=spread, clock_state=clock)
        assert result.state == MarketHealthState.CLOCK_DRIFT
        assert result.eligible_for_new_order is False

    def test_market_health_summary(self):
        machine = MarketHealthMachine("XAUUSD")
        result = machine.evaluate()
        summary = result.summary()
        assert "DISCONNECTED" in summary
        assert "BLOCKED" in summary


# ===== clock_guard tests =====


class TestClockGuard:
    def test_clock_guard_within_threshold(self):
        guard = ClockGuard(max_drift_ms=500.0)
        now = _utcnow()
        state = guard.check_clock(now)
        assert isinstance(state, ClockState)
        assert state.is_drifted is False
        assert abs(state.drift_ms) < 500.0
        assert guard.is_drifted() is False

    def test_clock_guard_drifted(self):
        guard = ClockGuard(max_drift_ms=100.0)
        drifted_time = _utcnow() + timedelta(seconds=5)
        state = guard.check_clock(drifted_time)
        assert state.is_drifted is True
        assert guard.is_drifted() is True

    def test_clock_guard_rejects_negative_threshold(self):
        with pytest.raises(ValueError):
            ClockGuard(max_drift_ms=-1.0)

    def test_clock_guard_get_drift_ms(self):
        guard = ClockGuard(max_drift_ms=500.0)
        assert guard.get_drift_ms() is None
        guard.check_clock(_utcnow())
        assert guard.get_drift_ms() is not None

    def test_clock_guard_summary(self):
        guard = ClockGuard(max_drift_ms=500.0)
        state = guard.check_clock(_utcnow())
        summary = state.summary()
        assert "OK" in summary or "DRIFTED" in summary


# ===== data_watermark tests =====


class TestDataWatermark:
    def test_data_watermark_fresh_detects_fresh(self):
        tracker = DataWatermarkTracker("XAUUSD")
        naive_now = datetime.utcnow()
        tick = _make_tick_record(dt=naive_now, received=naive_now)
        tracker.update(tick)
        assert tracker.is_fresh(max_age_seconds=5.0) is True
        assert tracker.has_gaps() is False

    def test_data_watermark_stale_detects_stale(self):
        tracker = DataWatermarkTracker("XAUUSD")
        old_naive = datetime.utcnow() - timedelta(seconds=10)
        tick = _make_tick_record(dt=old_naive, received=old_naive)
        tracker.update(tick)
        assert tracker.is_fresh(max_age_seconds=3.0) is False

    def test_data_watermark_gap_detected(self):
        tracker = DataWatermarkTracker("XAUUSD")
        tick = _make_tick_record(quality="GAP")
        tracker.update(tick)
        assert tracker.has_gaps() is True
        wm = tracker.get_watermark()
        assert wm.gap_count == 1

    def test_data_watermark_rejects_wrong_symbol(self):
        tracker = DataWatermarkTracker("XAUUSD")
        tick = _make_tick_record(symbol="EURUSD")
        with pytest.raises(ValueError, match="does not match"):
            tracker.update(tick)

    def test_data_watermark_produces_hash(self):
        tracker = DataWatermarkTracker("XAUUSD")
        wm = tracker.update(_make_tick_record())
        assert len(wm.watermark_hash) == 64  # SHA-256 hex

    def test_data_watermark_no_update_returns_none(self):
        tracker = DataWatermarkTracker("XAUUSD")
        assert tracker.get_watermark() is None
        assert tracker.is_fresh() is False

    def test_data_watermark_empty_symbol_raises(self):
        with pytest.raises(ValueError):
            DataWatermarkTracker("")
