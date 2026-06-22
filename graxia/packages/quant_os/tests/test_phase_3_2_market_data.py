"""
Phase 3.2 tests — Market Data subsystems, tick capture, and market health state machine.

Self-contained. No MT5 dependency. Uses pytest.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta, time
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from graxia.packages.quant_os.market_data.tick_recorder import (
    Tick, TickRecorder, TickRecorderState, TickGap,
)
from graxia.packages.quant_os.market_data.spread_monitor import (
    SpreadMonitor, SpreadState,
)
from graxia.packages.quant_os.market_data.feed_health_monitor import (
    FeedHealthMonitor, FeedHealthState, FeedHealthLevel,
)
from graxia.packages.quant_os.market_data.clock_guard import (
    ClockGuard, ClockState,
)
from graxia.packages.quant_os.market_data.market_session_guard import (
    MarketSessionGuard, SessionResult, SessionState, MarketSessionConfig,
)
from graxia.packages.quant_os.market_data.data_watermark import (
    DataWatermark, WatermarkState,
)
from graxia.packages.quant_os.market_data.account_snapshot import (
    AccountSnapshot, create_account_snapshot, _redact,
)
from graxia.packages.quant_os.market_data.smoke_report import (
    SmokeReport, SmokeReportGenerator, SmokeReportEntry,
)
from graxia.packages.quant_os.market_data.market_health import (
    MarketHealthMachine, MarketHealthResult, MarketHealthState,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_tick(ts: datetime, bid: float = 1.1, ask: float = 1.2, symbol: str = "EURUSD") -> Tick:
    return Tick(symbol=symbol, bid=bid, ask=ask, last=(bid + ask) / 2, volume=1.0, timestamp_utc=ts)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ===========================================================================
# 1. TickRecorder
# ===========================================================================


class TestTickRecorder:
    """Tests for TickRecorder: recording, gap detection, out-of-order detection."""

    def test_records_ticks(self):
        rec = TickRecorder("XAUUSD")
        t1 = _now()
        rec.record_tick(_make_tick(t1))
        ticks = rec.get_ticks()
        assert len(ticks) == 1
        assert ticks[0].bid == 1.1

    def test_records_multiple_ticks(self):
        rec = TickRecorder("XAUUSD")
        base = _now()
        for i in range(5):
            rec.record_tick(_make_tick(base + timedelta(seconds=i)))
        assert len(rec.get_ticks()) == 5

    def test_detects_gap(self):
        rec = TickRecorder("XAUUSD", max_gap_seconds=5.0)
        t1 = _now()
        rec.record_tick(_make_tick(t1))
        # Gap of 10 seconds
        gap_tick = _make_tick(t1 + timedelta(seconds=10))
        gap = rec.record_tick(gap_tick)
        assert gap is not None
        assert gap.gap_seconds == pytest.approx(10.0, abs=0.5)
        assert len(rec.get_gaps()) == 1

    def test_no_gap_when_within_threshold(self):
        rec = TickRecorder("XAUUSD", max_gap_seconds=5.0)
        t1 = _now()
        rec.record_tick(_make_tick(t1))
        gap = rec.record_tick(_make_tick(t1 + timedelta(seconds=3)))
        assert gap is None
        assert len(rec.get_gaps()) == 0

    def test_detects_out_of_order(self):
        rec = TickRecorder("XAUUSD")
        t1 = _now()
        t2 = t1 + timedelta(seconds=5)
        rec.record_tick(_make_tick(t2))
        # Earlier tick
        rec.record_tick(_make_tick(t1))
        state = rec.get_state()
        assert state.out_of_order_count == 1

    def test_symbol_mismatch_raises(self):
        rec = TickRecorder("XAUUSD")
        with pytest.raises(ValueError, match="symbol mismatch"):
            rec.record_tick(_make_tick(_now(), symbol="EURUSD"))

    def test_get_last_tick(self):
        rec = TickRecorder("XAUUSD")
        t1 = _now()
        rec.record_tick(_make_tick(t1))
        t2 = t1 + timedelta(seconds=1)
        rec.record_tick(_make_tick(t2))
        last = rec.get_last_tick()
        assert last.timestamp_utc == t2

    def test_get_last_tick_empty(self):
        rec = TickRecorder("XAUUSD")
        assert rec.get_last_tick() is None

    def test_get_ticks_last_n(self):
        rec = TickRecorder("XAUUSD")
        base = _now()
        for i in range(10):
            rec.record_tick(_make_tick(base + timedelta(seconds=i)))
        last3 = rec.get_ticks(last_n=3)
        assert len(last3) == 3

    def test_tick_age_seconds(self):
        rec = TickRecorder("XAUUSD")
        assert rec.tick_age_seconds() is None
        rec.record_tick(_make_tick(_now()))
        age = rec.tick_age_seconds()
        assert age is not None
        assert age >= 0

    def test_start_stop_streaming(self):
        rec = TickRecorder("XAUUSD")
        assert not rec.get_state().is_streaming
        rec.start_streaming()
        assert rec.get_state().is_streaming
        rec.stop_streaming()
        assert not rec.get_state().is_streaming

    def test_buffer_trim(self):
        rec = TickRecorder("XAUUSD", max_buffer_size=5)
        base = _now()
        for i in range(10):
            rec.record_tick(_make_tick(base + timedelta(seconds=i)))
        assert len(rec.get_ticks()) == 5

    def test_state_snapshot(self):
        rec = TickRecorder("XAUUSD")
        rec.record_tick(_make_tick(_now()))
        state = rec.get_state()
        assert state.total_ticks_recorded == 1
        assert state.symbol == "XAUUSD"
        assert state.gaps_detected == 0


# ===========================================================================
# 2. SpreadMonitor
# ===========================================================================


class TestSpreadMonitor:
    """Tests for SpreadMonitor: baseline calculation, wide spread detection."""

    def test_wide_spread_with_insufficient_data(self):
        mon = SpreadMonitor("XAUUSD", min_samples=20)
        state = mon.update(bid=2330.0, ask=2332.0)  # 2.0 spread
        assert state.is_wide is True  # fails closed with < 20 samples

    def test_normal_spread_after_baseline(self):
        mon = SpreadMonitor("XAUUSD", min_samples=5, multiplier=3.0)
        # Build baseline with consistent spreads
        for _ in range(10):
            mon.update(bid=2330.0, ask=2331.0)  # spread=1.0
        state = mon.update(bid=2330.0, ask=2331.0)
        assert state.is_wide is False

    def test_wide_spread_detected(self):
        mon = SpreadMonitor("XAUUSD", min_samples=5, multiplier=2.0)
        for _ in range(10):
            mon.update(bid=2330.0, ask=2331.0)  # spread=1.0
        # Anomalous spread
        state = mon.update(bid=2330.0, ask=2335.0)  # spread=5.0
        assert state.is_wide is True

    def test_update_with_spread(self):
        mon = SpreadMonitor("XAUUSD", min_samples=5, multiplier=2.0)
        for _ in range(10):
            mon.update_with_spread(1.0)
        state = mon.update_with_spread(1.0)
        assert state.is_wide is False

    def test_negative_spread_fails_closed(self):
        mon = SpreadMonitor("XAUUSD", min_samples=2)
        state = mon.update(bid=2330.0, ask=2329.0)  # ask < bid
        assert state.is_wide is True

    def test_invalid_bid_fails_closed(self):
        mon = SpreadMonitor("XAUUSD", min_samples=2)
        state = mon.update(bid=-1.0, ask=2330.0)
        assert state.is_wide is True

    def test_z_score_calculation(self):
        mon = SpreadMonitor("XAUUSD", min_samples=5, multiplier=3.0)
        for _ in range(20):
            mon.update(bid=2330.0, ask=2331.0)  # spread=1.0
        state = mon.update(bid=2330.0, ask=2331.0)
        assert state.z_score == pytest.approx(0.0, abs=0.1)

    def test_baseline_mean(self):
        mon = SpreadMonitor("XAUUSD", min_samples=5, multiplier=3.0)
        for _ in range(20):
            mon.update(bid=2330.0, ask=2331.0)  # spread=1.0
        state = mon.update(bid=2330.0, ask=2331.0)
        assert state.baseline_mean == pytest.approx(1.0, abs=0.01)

    def test_is_wide_method(self):
        mon = SpreadMonitor("XAUUSD", min_samples=5, multiplier=2.0)
        assert mon.is_wide() is True  # no data
        for _ in range(10):
            mon.update(bid=2330.0, ask=2331.0)
        assert mon.is_wide() is False

    def test_invalid_window_size(self):
        with pytest.raises(ValueError):
            SpreadMonitor("XAUUSD", window_size=1)

    def test_invalid_multiplier(self):
        with pytest.raises(ValueError):
            SpreadMonitor("XAUUSD", multiplier=-1.0)


# ===========================================================================
# 3. FeedHealthMonitor
# ===========================================================================


class TestFeedHealthMonitor:
    """Tests for FeedHealthMonitor: stale detection, health states."""

    def test_healthy_after_tick(self):
        mon = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=3.0)
        state = mon.record_tick()
        assert state.level == FeedHealthLevel.HEALTHY

    def test_stale_detection(self):
        mon = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=1.0)
        old_time = _now() - timedelta(seconds=5)
        mon.record_tick(old_time)
        state = mon.get_state()
        assert state.level == FeedHealthLevel.STALE

    def test_timeout_increments(self):
        mon = FeedHealthMonitor("XAUUSD")
        mon.record_timeout("connection lost")
        state = mon.record_timeout("connection lost")
        assert state.consecutive_timeouts == 2

    def test_disconnected_after_multiple_timeouts(self):
        mon = FeedHealthMonitor("XAUUSD")
        mon.record_timeout("e1")
        mon.record_timeout("e2")
        state = mon.record_timeout("e3")
        assert state.level == FeedHealthLevel.DISCONNECTED

    def test_degraded_on_single_timeout(self):
        mon = FeedHealthMonitor("XAUUSD")
        state = mon.record_timeout("error")
        assert state.level == FeedHealthLevel.DEGRADED

    def test_tick_resets_timeouts(self):
        mon = FeedHealthMonitor("XAUUSD")
        mon.record_timeout("error")
        state = mon.record_tick()
        assert state.consecutive_timeouts == 0

    def test_is_connected_healthy(self):
        mon = FeedHealthMonitor("XAUUSD")
        state = mon.record_tick()
        assert state.is_connected is True

    def test_is_connected_disconnected(self):
        mon = FeedHealthMonitor("XAUUSD")
        for _ in range(3):
            mon.record_timeout()
        state = mon.get_state()
        assert state.is_connected is False

    def test_is_eligible_for_order(self):
        mon = FeedHealthMonitor("XAUUSD")
        state = mon.record_tick()
        assert state.is_eligible_for_order is True

    def test_throughput_tracking(self):
        mon = FeedHealthMonitor("XAUUSD", throughput_window_seconds=1.0)
        for _ in range(10):
            mon.record_tick()
        state = mon.get_state()
        assert state.ticks_per_second > 0

    def test_unknown_state_initial(self):
        mon = FeedHealthMonitor("XAUUSD")
        state = mon.get_state()
        assert state.level == FeedHealthLevel.UNKNOWN

    def test_degraded_approaching_threshold(self):
        mon = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=3.0)
        # 70% of 3.0 = 2.1 seconds
        old_time = _now() - timedelta(seconds=2.5)
        mon.record_tick(old_time)
        state = mon.get_state()
        assert state.level == FeedHealthLevel.DEGRADED


# ===========================================================================
# 4. ClockGuard
# ===========================================================================


class TestClockGuard:
    """Tests for ClockGuard: drift detection."""

    def test_no_drift(self):
        guard = ClockGuard(max_drift_ms=500.0)
        mt5_time = datetime.now(timezone.utc)
        state = guard.check_clock(mt5_time)
        assert state.is_drifted is False

    def test_drift_ahead(self):
        guard = ClockGuard(max_drift_ms=100.0)
        mt5_time = datetime.now(timezone.utc) + timedelta(seconds=1.0)
        state = guard.check_clock(mt5_time)
        assert state.is_drifted is True
        assert state.drift_ms > 0

    def test_drift_behind(self):
        guard = ClockGuard(max_drift_ms=100.0)
        mt5_time = datetime.now(timezone.utc) - timedelta(seconds=1.0)
        state = guard.check_clock(mt5_time)
        assert state.is_drifted is True
        assert state.drift_ms < 0

    def test_is_drifted_method(self):
        guard = ClockGuard(max_drift_ms=100.0)
        assert guard.is_drifted() is False
        mt5_time = datetime.now(timezone.utc) + timedelta(seconds=1.0)
        guard.check_clock(mt5_time)
        assert guard.is_drifted() is True

    def test_get_drift_ms(self):
        guard = ClockGuard(max_drift_ms=100.0)
        assert guard.get_drift_ms() is None
        mt5_time = datetime.now(timezone.utc) + timedelta(milliseconds=50)
        guard.check_clock(mt5_time)
        drift = guard.get_drift_ms()
        assert drift is not None
        assert abs(drift) < 1000

    def test_get_state(self):
        guard = ClockGuard(max_drift_ms=500.0)
        mt5_time = datetime.now(timezone.utc)
        state = guard.check_clock(mt5_time)
        assert guard.get_state() is not None

    def test_drift_seconds_property(self):
        guard = ClockGuard(max_drift_ms=500.0)
        mt5_time = datetime.now(timezone.utc) + timedelta(milliseconds=250)
        state = guard.check_clock(mt5_time)
        assert state.drift_seconds == pytest.approx(0.25, abs=0.1)

    def test_summary(self):
        guard = ClockGuard(max_drift_ms=500.0)
        mt5_time = datetime.now(timezone.utc)
        state = guard.check_clock(mt5_time)
        summary = state.summary()
        assert "Clock" in summary

    def test_invalid_max_drift(self):
        with pytest.raises(ValueError):
            ClockGuard(max_drift_ms=0)

    def test_naive_datetime_treated_as_utc(self):
        guard = ClockGuard(max_drift_ms=500.0)
        naive_time = datetime.utcnow()
        state = guard.check_clock(naive_time)
        assert state.is_drifted is False


# ===========================================================================
# 5. MarketSessionGuard
# ===========================================================================


class TestMarketSessionGuard:
    """Tests for MarketSessionGuard: session determination, weekend closure."""

    def test_weekend_closed(self):
        guard = MarketSessionGuard("XAUUSD")
        # Saturday
        saturday = datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc)
        result = guard.check(saturday)
        assert result.state == SessionState.CLOSED_WEEKEND
        assert result.is_open is False

    def test_weekday_open(self):
        guard = MarketSessionGuard("XAUUSD")
        # Wednesday noon UTC — should be within forex session
        wednesday = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
        result = guard.check(wednesday)
        assert result.state == SessionState.OPEN
        assert result.is_open is True

    def test_holiday_closed(self):
        config = MarketSessionConfig(holidays=((1, 1),))
        guard = MarketSessionGuard("XAUUSD", config=config)
        new_year = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        result = guard.check(new_year)
        assert result.state == SessionState.CLOSED_HOLIDAY

    def test_outside_session_hours(self):
        config = MarketSessionConfig(
            forex_open_utc=time(8, 0),
            forex_close_utc=time(17, 0),
        )
        guard = MarketSessionGuard("XAUUSD", config=config)
        # 3 AM UTC — outside session
        night = datetime(2026, 6, 24, 3, 0, tzinfo=timezone.utc)
        result = guard.check(night)
        assert result.state == SessionState.CLOSED_SESSION

    def test_is_open_method(self):
        guard = MarketSessionGuard("XAUUSD")
        wednesday = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
        assert guard.is_open(wednesday) is True

    def test_is_eligible_for_order(self):
        guard = MarketSessionGuard("XAUUSD")
        wednesday = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
        result = guard.check(wednesday)
        assert result.is_eligible_for_order is True

    def test_summary(self):
        guard = MarketSessionGuard("XAUUSD")
        wednesday = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
        result = guard.check(wednesday)
        assert "Session" in result.summary()

    def test_sunday_closed(self):
        guard = MarketSessionGuard("XAUUSD")
        sunday = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
        result = guard.check(sunday)
        assert result.state == SessionState.CLOSED_WEEKEND


# ===========================================================================
# 6. MarketHealthMachine
# ===========================================================================


class TestMarketHealthMachine:
    """Tests for MarketHealthMachine: state transitions, eligibility logic."""

    def test_healthy_when_all_ok(self):
        machine = MarketHealthMachine("XAUUSD")
        # Minimal inputs that indicate healthy
        @dataclass
        class HealthyFeed:
            level: FeedHealthLevel = FeedHealthLevel.HEALTHY
            last_tick_age_seconds: float = 1.0
            max_tick_age_seconds: float = 3.0

        @dataclass
        class HealthySpread:
            is_wide: bool = False

        @dataclass
        class HealthyClock:
            is_drifted: bool = False

        @dataclass
        class HealthySession:
            is_open: bool = True

        result = machine.evaluate(
            feed_health=HealthyFeed(),
            spread_state=HealthySpread(),
            clock_state=HealthyClock(),
            session_state=HealthySession(),
        )
        assert result.state == MarketHealthState.HEALTHY
        assert result.eligible_for_new_order is True

    def test_disconnected_when_no_feed(self):
        machine = MarketHealthMachine("XAUUSD")
        result = machine.evaluate(feed_health=None)
        assert result.state == MarketHealthState.DISCONNECTED
        assert result.eligible_for_new_order is False
        assert "FEED_DISCONNECTED" in result.reason_codes

    def test_market_closed(self):
        machine = MarketHealthMachine("XAUUSD")

        @dataclass
        class ClosedSession:
            is_open: bool = False
            state: SessionState = SessionState.CLOSED_WEEKEND

        result = machine.evaluate(session_state=ClosedSession())
        assert result.state == MarketHealthState.MARKET_CLOSED
        assert result.eligible_for_new_order is False

    def test_stale_feed(self):
        machine = MarketHealthMachine("XAUUSD")

        @dataclass
        class StaleFeed:
            level: FeedHealthLevel = FeedHealthLevel.STALE
            last_tick_age_seconds: float = 10.0
            max_tick_age_seconds: float = 3.0

        result = machine.evaluate(feed_health=StaleFeed())
        assert result.state == MarketHealthState.STALE_FEED
        assert result.eligible_for_new_order is False

    def test_wide_spread(self):
        machine = MarketHealthMachine("XAUUSD")

        @dataclass
        class HealthyFeed:
            level: FeedHealthLevel = FeedHealthLevel.HEALTHY
            last_tick_age_seconds: float = 1.0
            max_tick_age_seconds: float = 3.0

        @dataclass
        class WideSpread:
            is_wide: bool = True

        result = machine.evaluate(
            feed_health=HealthyFeed(),
            spread_state=WideSpread(),
        )
        assert result.state == MarketHealthState.WIDE_SPREAD
        assert result.eligible_for_new_order is False

    def test_clock_drift(self):
        machine = MarketHealthMachine("XAUUSD")

        @dataclass
        class HealthyFeed:
            level: FeedHealthLevel = FeedHealthLevel.HEALTHY
            last_tick_age_seconds: float = 1.0
            max_tick_age_seconds: float = 3.0

        @dataclass
        class NormalSpread:
            is_wide: bool = False

        @dataclass
        class DriftedClock:
            is_drifted: bool = True
            drift_ms: float = 1000.0

        result = machine.evaluate(
            feed_health=HealthyFeed(),
            spread_state=NormalSpread(),
            clock_state=DriftedClock(),
        )
        assert result.state == MarketHealthState.CLOCK_DRIFT
        assert result.eligible_for_new_order is False

    def test_tick_gap(self):
        machine = MarketHealthMachine("XAUUSD")

        @dataclass
        class HealthyFeed:
            level: FeedHealthLevel = FeedHealthLevel.HEALTHY
            last_tick_age_seconds: float = 1.0
            max_tick_age_seconds: float = 3.0

        @dataclass
        class NormalSpread:
            is_wide: bool = False

        @dataclass
        class GapInfo:
            gaps_detected: int = 3
            out_of_order_count: int = 0

        result = machine.evaluate(
            feed_health=HealthyFeed(),
            spread_state=NormalSpread(),
            tick_gap_info=GapInfo(),
        )
        assert result.state == MarketHealthState.MISSING_TICK_GAP
        assert result.eligible_for_new_order is False

    def test_out_of_order(self):
        machine = MarketHealthMachine("XAUUSD")

        @dataclass
        class HealthyFeed:
            level: FeedHealthLevel = FeedHealthLevel.HEALTHY
            last_tick_age_seconds: float = 1.0
            max_tick_age_seconds: float = 3.0

        @dataclass
        class NormalSpread:
            is_wide: bool = False

        @dataclass
        class OOOInfo:
            gaps_detected: int = 0
            out_of_order_count: int = 5

        result = machine.evaluate(
            feed_health=HealthyFeed(),
            spread_state=NormalSpread(),
            tick_gap_info=OOOInfo(),
        )
        assert result.state == MarketHealthState.OUT_OF_ORDER_DATA
        assert result.eligible_for_new_order is False

    def test_contract_changed(self):
        machine = MarketHealthMachine("XAUUSD")

        @dataclass
        class HealthyFeed:
            level: FeedHealthLevel = FeedHealthLevel.HEALTHY
            last_tick_age_seconds: float = 1.0
            max_tick_age_seconds: float = 3.0

        @dataclass
        class NormalSpread:
            is_wide: bool = False

        result = machine.evaluate(
            feed_health=HealthyFeed(),
            spread_state=NormalSpread(),
            contract_changed=True,
        )
        assert result.state == MarketHealthState.CONTRACT_CHANGED
        assert result.eligible_for_new_order is False

    def test_priority_disconnected_over_others(self):
        """DISCONNECTED takes priority over all other conditions."""
        machine = MarketHealthMachine("XAUUSD")

        @dataclass
        class DisconnectedFeed:
            level: FeedHealthLevel = FeedHealthLevel.DISCONNECTED
            last_tick_age_seconds: float = 100.0
            max_tick_age_seconds: float = 3.0

        @dataclass
        class WideSpread:
            is_wide: bool = True

        @dataclass
        class DriftedClock:
            is_drifted: bool = True
            drift_ms: float = 2000.0

        result = machine.evaluate(
            feed_health=DisconnectedFeed(),
            spread_state=WideSpread(),
            clock_state=DriftedClock(),
        )
        assert result.state == MarketHealthState.DISCONNECTED
        assert "FEED_DISCONNECTED" in result.reason_codes

    def test_multiple_reason_codes_collected(self):
        machine = MarketHealthMachine("XAUUSD")

        @dataclass
        class StaleFeed:
            level: FeedHealthLevel = FeedHealthLevel.STALE
            last_tick_age_seconds: float = 10.0
            max_tick_age_seconds: float = 3.0

        @dataclass
        class WideSpread:
            is_wide: bool = True

        @dataclass
        class DriftedClock:
            is_drifted: bool = True
            drift_ms: float = 1500.0

        result = machine.evaluate(
            feed_health=StaleFeed(),
            spread_state=WideSpread(),
            clock_state=DriftedClock(),
        )
        assert len(result.reason_codes) >= 3

    def test_is_eligible_for_order_method(self):
        machine = MarketHealthMachine("XAUUSD")
        assert machine.is_eligible_for_order() is False  # initial state is UNKNOWN

    def test_get_state(self):
        machine = MarketHealthMachine("XAUUSD")
        assert machine.get_state() == MarketHealthState.UNKNOWN

    def test_result_summary(self):
        machine = MarketHealthMachine("XAUUSD")
        result = machine.evaluate()
        summary = result.summary()
        assert "Market" in summary
        assert "BLOCKED" in summary or "ELIGIBLE" in summary

    def test_result_details_populated(self):
        machine = MarketHealthMachine("XAUUSD")

        @dataclass
        class StaleFeed:
            level: FeedHealthLevel = FeedHealthLevel.STALE
            last_tick_age_seconds: float = 10.0
            max_tick_age_seconds: float = 3.0

        result = machine.evaluate(feed_health=StaleFeed())
        assert "tick_age_seconds" in result.details

    def test_timestamp_is_set(self):
        machine = MarketHealthMachine("XAUUSD")
        result = machine.evaluate()
        assert result.timestamp_utc is not None
        assert result.timestamp_utc.tzinfo is not None


# ===========================================================================
# 7. DataWatermark
# ===========================================================================


class TestDataWatermark:
    """Tests for DataWatermark: update tracking, freshness check."""

    def test_fresh_after_update(self):
        wm = DataWatermark("XAUUSD", max_age_seconds=10.0)
        state = wm.update(_now())
        assert state.is_fresh is True

    def test_stale_after_timeout(self):
        wm = DataWatermark("XAUUSD", max_age_seconds=1.0)
        wm.update(_now() - timedelta(seconds=5))
        state = wm.get_state()
        assert state.is_fresh is False

    def test_is_fresh_method(self):
        wm = DataWatermark("XAUUSD", max_age_seconds=10.0)
        assert wm.is_fresh() is False  # no data
        wm.update(_now())
        assert wm.is_fresh() is True

    def test_update_count(self):
        wm = DataWatermark("XAUUSD")
        wm.update(_now())
        wm.update(_now())
        state = wm.update(_now())
        assert state.update_count == 3

    def test_summary(self):
        wm = DataWatermark("XAUUSD")
        wm.update(_now())
        state = wm.get_state()
        assert "Watermark" in state.summary()

    def test_initial_state_not_fresh(self):
        wm = DataWatermark("XAUUSD")
        assert wm.is_fresh() is False

    def test_invalid_max_age(self):
        with pytest.raises(ValueError):
            DataWatermark("XAUUSD", max_age_seconds=0)

    def test_naive_datetime_treated_as_utc(self):
        wm = DataWatermark("XAUUSD", max_age_seconds=10.0)
        naive = datetime.utcnow()
        state = wm.update(naive)
        assert state.is_fresh is True


# ===========================================================================
# 8. AccountSnapshot
# ===========================================================================


class TestAccountSnapshot:
    """Tests for AccountSnapshot: creation, redaction, serialization."""

    def test_create_snapshot(self):
        snap = create_account_snapshot(
            balance=10000.0, equity=10500.0, leverage=100, currency="USD",
        )
        assert snap.balance == 10000.0
        assert snap.equity == 10500.0

    def test_redaction_server(self):
        snap = create_account_snapshot(
            balance=10000.0, equity=10000.0,
            server="ICMarketsSC-Demo02", login="12345678",
        )
        assert snap.server_redacted.endswith("02")
        assert snap.login_redacted.endswith("78")
        assert "*" in snap.server_redacted
        assert "*" in snap.login_redacted

    def test_redaction_short_string(self):
        assert _redact("AB") == "**"
        assert _redact("A") == "**"
        assert _redact("") == "**"

    def test_to_dict(self):
        snap = create_account_snapshot(balance=100.0, equity=100.0)
        d = snap.to_dict()
        assert "balance" in d
        assert "server_redacted" in d

    def test_snapshot_id_auto_generated(self):
        snap = create_account_snapshot(balance=100.0, equity=100.0)
        assert snap.snapshot_id.startswith("snap-")

    def test_snapshot_id_custom(self):
        snap = create_account_snapshot(
            balance=100.0, equity=100.0, snapshot_id="custom-001",
        )
        assert snap.snapshot_id == "custom-001"

    def test_frozen_dataclass(self):
        snap = create_account_snapshot(balance=100.0, equity=100.0)
        with pytest.raises(AttributeError):
            snap.balance = 200.0


# ===========================================================================
# 9. SmokeReport
# ===========================================================================


class TestSmokeReport:
    """Tests for SmokeReport: generation works."""

    def test_generate_report(self):
        gen = SmokeReportGenerator("XAUUSD")
        report = gen.generate()
        assert report.symbol == "XAUUSD"
        assert len(report.entries) > 0

    def test_report_has_all_components(self):
        gen = SmokeReportGenerator("XAUUSD")
        report = gen.generate()
        components = {e.component for e in report.entries}
        expected = {
            "feed_health", "spread", "clock", "session",
            "tick_recorder", "watermark", "account",
        }
        assert expected.issubset(components)

    def test_report_to_dict(self):
        gen = SmokeReportGenerator("XAUUSD")
        report = gen.generate()
        d = report.to_dict()
        assert "entries" in d
        assert "overall_status" in d

    def test_report_to_json(self):
        gen = SmokeReportGenerator("XAUUSD")
        report = gen.generate()
        import json
        j = report.to_json()
        parsed = json.loads(j)
        assert parsed["symbol"] == "XAUUSD"

    def test_report_hash(self):
        gen = SmokeReportGenerator("XAUUSD")
        report = gen.generate()
        h = report.compute_hash()
        assert len(h) == 64  # SHA-256

    def test_report_with_healthy_inputs(self):
        gen = SmokeReportGenerator("XAUUSD")

        @dataclass
        class HealthyFeed:
            level: FeedHealthLevel = FeedHealthLevel.HEALTHY

        @dataclass
        class NormalSpread:
            is_wide: bool = False

        @dataclass
        class HealthyClock:
            is_drifted: bool = False

        @dataclass
        class OpenSession:
            is_open: bool = True
            state: SessionState = SessionState.OPEN

        @dataclass
        class GoodTicks:
            gaps_detected: int = 0
            out_of_order_count: int = 0
            total_ticks_recorded: int = 100

        @dataclass
        class FreshWatermark:
            is_fresh: bool = True

        @dataclass
        class GoodAccount:
            balance: float = 10000.0
            equity: float = 10500.0

        report = gen.generate(
            feed_health_state=HealthyFeed(),
            spread_state=NormalSpread(),
            clock_state=HealthyClock(),
            session_result=OpenSession(),
            tick_recorder_state=GoodTicks(),
            watermark_state=FreshWatermark(),
            account_snapshot=GoodAccount(),
        )
        assert report.overall_status == "PASS"

    def test_report_fail_when_any_degraded(self):
        gen = SmokeReportGenerator("XAUUSD")

        @dataclass
        class StaleFeed:
            level: FeedHealthLevel = FeedHealthLevel.STALE

        report = gen.generate(feed_health_state=StaleFeed())
        assert report.overall_status == "FAIL"

    def test_report_id_unique(self):
        gen = SmokeReportGenerator("XAUUSD")
        r1 = gen.generate()
        r2 = gen.generate()
        assert r1.report_id != r2.report_id


# ===========================================================================
# 10. Integration: MarketHealthMachine with real components
# ===========================================================================


class TestMarketHealthIntegration:
    """Integration tests: MarketHealthMachine with live FeedHealthMonitor, etc."""

    def test_integration_healthy_flow(self):
        """Simulate a healthy tick flow and verify market health."""
        feed = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=3.0)
        spread = SpreadMonitor("XAUUSD", min_samples=5, multiplier=3.0)
        clock = ClockGuard(max_drift_ms=500.0)
        session = MarketSessionGuard("XAUUSD")
        machine = MarketHealthMachine("XAUUSD")

        # Feed healthy tick
        feed.record_tick()

        # Spread baseline
        for _ in range(10):
            spread.update(bid=2330.0, ask=2331.0)
        spread_state = spread.update(bid=2330.0, ask=2331.0)

        # Clock OK
        clock_state = clock.check_clock(datetime.now(timezone.utc))

        # Session open (Wednesday noon)
        session_result = session.check(datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc))

        result = machine.evaluate(
            feed_health=feed.get_state(),
            spread_state=spread_state,
            clock_state=clock_state,
            session_state=session_result,
        )
        assert result.state == MarketHealthState.HEALTHY
        assert result.eligible_for_new_order is True

    def test_integration_wide_spread_blocks_order(self):
        """Simulate wide spread and verify order blocked."""
        feed = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=3.0)
        feed.record_tick()

        spread = SpreadMonitor("XAUUSD", min_samples=5, multiplier=2.0)
        for _ in range(10):
            spread.update(bid=2330.0, ask=2331.0)
        spread_state = spread.update(bid=2330.0, ask=2335.0)  # wide!

        clock = ClockGuard(max_drift_ms=500.0)
        clock_state = clock.check_clock(datetime.now(timezone.utc))

        session = MarketSessionGuard("XAUUSD")
        session_result = session.check(datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc))

        machine = MarketHealthMachine("XAUUSD")
        result = machine.evaluate(
            feed_health=feed.get_state(),
            spread_state=spread_state,
            clock_state=clock_state,
            session_state=session_result,
        )
        assert result.eligible_for_new_order is False
        assert "WIDE_SPREAD" in result.reason_codes

    def test_integration_weekend_closed(self):
        """Weekend → MARKET_CLOSED → not eligible."""
        session = MarketSessionGuard("XAUUSD")
        session_result = session.check(datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc))

        machine = MarketHealthMachine("XAUUSD")
        result = machine.evaluate(session_state=session_result)
        assert result.state == MarketHealthState.MARKET_CLOSED
        assert result.eligible_for_new_order is False
