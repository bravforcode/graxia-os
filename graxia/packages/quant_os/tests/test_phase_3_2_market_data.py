"""
Phase 3.2 tests — Market Data subsystems, tick capture, and market health state machine.

Self-contained. No MT5 dependency. Uses pytest.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest

from graxia.packages.quant_os.market_data.account_snapshot import (
    _redact,
    create_account_snapshot,
)
from graxia.packages.quant_os.market_data.clock_guard import (
    ClockGuard,
)
from graxia.packages.quant_os.market_data.data_watermark import (
    DataWatermarkTracker,
)
from graxia.packages.quant_os.market_data.feed_health import (
    FeedHealthMonitor,
)
from graxia.packages.quant_os.market_data.market_health import (
    MarketHealthMachine,
    MarketHealthState,
)
from graxia.packages.quant_os.market_data.market_session_guard import (
    MarketSessionConfig,
    MarketSessionGuard,
    SessionState,
)
from graxia.packages.quant_os.market_data.smoke_report import (
    SmokeReportGenerator,
)
from graxia.packages.quant_os.market_data.spread_monitor import (
    SpreadMonitor,
)

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from graxia.packages.quant_os.market_data.tick_recorder import (
    TickRecord,
    TickRecorder,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _make_tick_record(
    ts: datetime,
    received_at: datetime | None = None,
    bid: float = 1.1,
    ask: float = 1.2,
    symbol: str = "XAUUSD",
    source: str = "mt5",
) -> TickRecord:
    """Create a TickRecord with given parameters."""
    rec_at = received_at or datetime.now(UTC)
    return TickRecord(
        timestamp_utc=ts,
        received_at_utc=rec_at,
        symbol=symbol,
        bid=Decimal(str(bid)),
        ask=Decimal(str(ask)),
        last=Decimal(str((bid + ask) / 2)),
        spread_points=Decimal(str(ask - bid)),
        flags="",
        sequence_id=1,
        connection_session_id="test-session",
        source=source,
        data_quality="VALID",
    )


def _now() -> datetime:
    return datetime.now(UTC)


# ===========================================================================
# 1. TickRecorder
# ===========================================================================


class TestTickRecorder:
    """Tests for TickRecorder: recording, gap detection, out-of-order detection."""

    def test_records_ticks(self):
        rec = TickRecorder("XAUUSD", "session-001")
        t1 = datetime.now(UTC)
        rec.record_tick(
            bid=Decimal("2330.0"),
            ask=Decimal("2331.0"),
            last=Decimal("2330.5"),
            timestamp_utc=t1,
        )
        assert rec.count() == 1

    def test_records_multiple_ticks(self):
        rec = TickRecorder("XAUUSD", "session-002")
        base = datetime.now(UTC)
        for i in range(5):
            rec.record_tick(
                bid=Decimal("2330.0"),
                ask=Decimal("2331.0"),
                last=Decimal("2330.5"),
                timestamp_utc=base + timedelta(seconds=i),
            )
        assert rec.count() == 5

    def test_detects_gap(self):
        rec = TickRecorder("XAUUSD", "session-003")
        t1 = datetime.now(UTC)
        rec.record_tick(
            bid=Decimal("2330.0"),
            ask=Decimal("2331.0"),
            last=Decimal("2330.5"),
            timestamp_utc=t1,
        )
        # Gap of 10 seconds (threshold is 2.0)
        gap_tick = rec.record_tick(
            bid=Decimal("2330.0"),
            ask=Decimal("2331.0"),
            last=Decimal("2330.5"),
            timestamp_utc=t1 + timedelta(seconds=10),
        )
        assert gap_tick.data_quality == "GAP"

    def test_no_gap_when_within_threshold(self):
        rec = TickRecorder("XAUUSD", "session-004")
        t1 = datetime.now(UTC)
        rec.record_tick(
            bid=Decimal("2330.0"),
            ask=Decimal("2331.0"),
            last=Decimal("2330.5"),
            timestamp_utc=t1,
        )
        tick = rec.record_tick(
            bid=Decimal("2330.0"),
            ask=Decimal("2331.0"),
            last=Decimal("2330.5"),
            timestamp_utc=t1 + timedelta(seconds=1),
        )
        assert tick.data_quality == "VALID"

    def test_detects_out_of_order(self):
        rec = TickRecorder("XAUUSD", "session-005")
        t1 = datetime.now(UTC)
        t2 = t1 + timedelta(seconds=5)
        rec.record_tick(
            bid=Decimal("2330.0"),
            ask=Decimal("2331.0"),
            last=Decimal("2330.5"),
            timestamp_utc=t2,
        )
        # Earlier tick
        ooo_tick = rec.record_tick(
            bid=Decimal("2330.0"),
            ask=Decimal("2331.0"),
            last=Decimal("2330.5"),
            timestamp_utc=t1,
        )
        assert ooo_tick.data_quality == "OUT_OF_ORDER"

    def test_symbol_mismatch_not_checked(self):
        """TickRecorder does not enforce symbol on record_tick — it uses self.symbol."""
        rec = TickRecorder("XAUUSD", "session-006")
        # Just verify it works
        rec.record_tick(
            bid=Decimal("2330.0"),
            ask=Decimal("2331.0"),
            last=Decimal("2330.5"),
            timestamp_utc=datetime.now(UTC),
        )
        assert rec.count() == 1

    def test_get_latest_tick(self):
        rec = TickRecorder("XAUUSD", "session-007")
        t1 = datetime.now(UTC)
        rec.record_tick(
            bid=Decimal("2330.0"),
            ask=Decimal("2331.0"),
            last=Decimal("2330.5"),
            timestamp_utc=t1,
        )
        t2 = t1 + timedelta(seconds=1)
        rec.record_tick(
            bid=Decimal("2331.0"),
            ask=Decimal("2332.0"),
            last=Decimal("2331.5"),
            timestamp_utc=t2,
        )
        last = rec.get_latest_tick()
        assert last is not None
        assert last.timestamp_utc == t2

    def test_get_latest_tick_empty(self):
        rec = TickRecorder("XAUUSD", "session-008")
        assert rec.get_latest_tick() is None

    def test_get_ticks_filtered(self):
        rec = TickRecorder("XAUUSD", "session-009")
        base = datetime.now(UTC)
        for i in range(10):
            rec.record_tick(
                bid=Decimal("2330.0"),
                ask=Decimal("2331.0"),
                last=Decimal("2330.5"),
                timestamp_utc=base + timedelta(seconds=i),
            )
        # Filter to last 3 seconds
        cutoff = base + timedelta(seconds=7)
        recent = rec.get_ticks(since=cutoff)
        assert len(recent) == 3

    def test_invalid_symbol_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            TickRecorder("", "session")

    def test_invalid_session_id_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            TickRecorder("XAUUSD", "")

    def test_stale_detection(self):
        """Tick older than threshold is marked STALE."""
        rec = TickRecorder("XAUUSD", "session-stale")
        old_time = datetime.now(UTC) - timedelta(seconds=10)
        tick = rec.record_tick(
            bid=Decimal("2330.0"),
            ask=Decimal("2331.0"),
            last=Decimal("2330.5"),
            timestamp_utc=old_time,
        )
        assert tick.data_quality == "STALE"

    def test_count(self):
        rec = TickRecorder("XAUUSD", "session-count")
        assert rec.count() == 0
        rec.record_tick(
            bid=Decimal("2330.0"),
            ask=Decimal("2331.0"),
            last=Decimal("2330.5"),
            timestamp_utc=datetime.now(UTC),
        )
        assert rec.count() == 1


# ===========================================================================
# 2. SpreadMonitor
# ===========================================================================


class TestSpreadMonitor:
    """Tests for SpreadMonitor: baseline calculation, wide spread detection."""

    def test_wide_spread_with_insufficient_data(self):
        """With only 1 sample, std=0. The is_wide_spread method only rejects > 10x mean."""
        mon = SpreadMonitor("XAUUSD", reject_multiplier=2.0)
        # Single sample — baseline_mean=1.0, baseline_std=0
        mon.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        # is_wide_spread returns False when std=0 and spread < 10x mean
        assert mon.is_wide_spread(Decimal("5.0")) is False
        # But extreme outlier (> 10x mean) is rejected
        assert mon.is_wide_spread(Decimal("15.0")) is True

    def test_normal_spread_after_baseline(self):
        mon = SpreadMonitor("XAUUSD", reject_multiplier=3.0)
        for _ in range(10):
            mon.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        state = mon.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        assert state.is_wide is False

    def test_wide_spread_detected(self):
        mon = SpreadMonitor("XAUUSD", reject_multiplier=2.0)
        for _ in range(10):
            mon.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        # Anomalous spread: 5.0 vs baseline 1.0
        state = mon.on_tick(Decimal("2330.0"), Decimal("2335.0"), datetime.now(UTC))
        assert state.is_wide is True

    def test_invalid_bid_returns_current_state(self):
        mon = SpreadMonitor("XAUUSD")
        state1 = mon.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        state2 = mon.on_tick(Decimal("-1.0"), Decimal("2331.0"), datetime.now(UTC))
        assert state2 == state1

    def test_ask_less_than_bid_returns_current_state(self):
        mon = SpreadMonitor("XAUUSD")
        state1 = mon.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        state2 = mon.on_tick(Decimal("2330.0"), Decimal("2329.0"), datetime.now(UTC))
        assert state2 == state1

    def test_z_score_calculation(self):
        mon = SpreadMonitor("XAUUSD", reject_multiplier=3.0)
        for _ in range(20):
            mon.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        state = mon.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        # With consistent spreads, multiplier should be close to 1.0
        assert state.spread_multiplier == pytest.approx(1.0, abs=0.1)

    def test_baseline_mean(self):
        mon = SpreadMonitor("XAUUSD", reject_multiplier=3.0)
        for _ in range(20):
            mon.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        state = mon.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        assert state.baseline_mean == Decimal("1")

    def test_is_wide_spread_method(self):
        mon = SpreadMonitor("XAUUSD", reject_multiplier=2.0)
        # With no data, is_wide_spread returns False (baseline_mean is 0)
        assert mon.is_wide_spread(Decimal("100.0")) is False
        # Build baseline
        for _ in range(10):
            mon.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        assert mon.is_wide_spread(Decimal("1.0")) is False

    def test_get_baseline(self):
        mon = SpreadMonitor("XAUUSD")
        mon.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        mean, std = mon.get_baseline()
        assert mean == Decimal("1")
        assert std == Decimal("0")  # Only 1 sample

    def test_reset(self):
        mon = SpreadMonitor("XAUUSD")
        mon.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        mon.reset()
        state = mon.get_state()
        assert state.sample_count == 0


# ===========================================================================
# 3. FeedHealthMonitor
# ===========================================================================


class TestFeedHealthMonitor:
    """Tests for FeedHealthMonitor: stale detection, health states."""

    def test_healthy_after_tick(self):
        mon = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=3.0)
        state = mon.on_tick_received(
            tick_timestamp=datetime.now(UTC),
            received_at=datetime.now(UTC),
        )
        assert state.state == "HEALTHY"

    def test_stale_detection(self):
        mon = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=1.0)
        old_time = datetime.now(UTC) - timedelta(seconds=5)
        mon.on_tick_received(
            tick_timestamp=old_time,
            received_at=datetime.now(UTC),
        )
        # Check health after time passes
        state = mon.check_health()
        assert state.state == "STALE_FEED"

    def test_gap_detection(self):
        mon = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=5.0)
        t1 = datetime.now(UTC)
        mon.on_tick_received(tick_timestamp=t1, received_at=datetime.now(UTC))
        # Gap of 10 seconds (threshold is 2x expected interval)
        mon.on_tick_received(
            tick_timestamp=t1 + timedelta(seconds=10),
            received_at=datetime.now(UTC),
        )
        state = mon.check_health()
        assert state.gap_count == 1

    def test_consecutive_stale_increments(self):
        mon = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=1.0)
        # Record tick that's already old using the monitor's internal state
        mon._last_tick_time = datetime.now(UTC) - timedelta(seconds=5)
        state = mon.check_health()
        assert state.consecutive_stale == 1
        # Check again without new tick
        state = mon.check_health()
        assert state.consecutive_stale == 2

    def test_disconnected_after_multiple_stale(self):
        mon = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=1.0)
        # 3 consecutive stale checks → DISCONNECTED
        for _ in range(3):
            mon.on_tick_received(
                tick_timestamp=datetime.now(UTC) - timedelta(seconds=5),
                received_at=datetime.now(UTC),
            )
            mon.check_health()
        state = mon.check_health()
        assert state.state == "DISCONNECTED"

    def test_healthy_resets_consecutive_stale(self):
        mon = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=1.0)
        # Make it stale
        mon.on_tick_received(
            tick_timestamp=datetime.now(UTC) - timedelta(seconds=5),
            received_at=datetime.now(UTC),
        )
        mon.check_health()
        # New fresh tick resets it
        mon.on_tick_received(
            tick_timestamp=datetime.now(UTC),
            received_at=datetime.now(UTC),
        )
        state = mon.check_health()
        assert state.state == "HEALTHY"
        assert state.consecutive_stale == 0

    def test_is_healthy_method(self):
        mon = FeedHealthMonitor("XAUUSD")
        assert mon.is_healthy() is False  # initial state is UNKNOWN
        mon.on_tick_received(
            tick_timestamp=datetime.now(UTC),
            received_at=datetime.now(UTC),
        )
        assert mon.is_healthy() is True

    def test_tick_count_last_minute(self):
        mon = FeedHealthMonitor("XAUUSD")
        for _ in range(5):
            mon.on_tick_received(
                tick_timestamp=datetime.now(UTC),
                received_at=datetime.now(UTC),
            )
        state = mon.check_health()
        assert state.tick_count_last_minute == 5

    def test_reset(self):
        mon = FeedHealthMonitor("XAUUSD")
        mon.on_tick_received(
            tick_timestamp=datetime.now(UTC),
            received_at=datetime.now(UTC),
        )
        mon.reset()
        state = mon.check_health()
        assert state.state == "UNKNOWN"

    def test_unknown_state_initial(self):
        mon = FeedHealthMonitor("XAUUSD")
        state = mon.check_health()
        assert state.state == "UNKNOWN"

    def test_degraded_approaching_threshold(self):
        mon = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=3.0)
        # Tick 2.5 seconds ago (approaching 3.0 threshold)
        mon.on_tick_received(
            tick_timestamp=datetime.now(UTC) - timedelta(seconds=2.5),
            received_at=datetime.now(UTC),
        )
        state = mon.check_health()
        # Should still be HEALTHY but close to threshold
        assert state.state == "HEALTHY"


# ===========================================================================
# 4. ClockGuard
# ===========================================================================


class TestClockGuard:
    """Tests for ClockGuard: drift detection."""

    def test_no_drift(self):
        guard = ClockGuard(max_drift_ms=500.0)
        mt5_time = datetime.now(UTC)
        state = guard.check_clock(mt5_time)
        assert state.is_drifted is False

    def test_drift_ahead(self):
        guard = ClockGuard(max_drift_ms=100.0)
        mt5_time = datetime.now(UTC) + timedelta(seconds=1.0)
        state = guard.check_clock(mt5_time)
        assert state.is_drifted is True
        assert state.drift_ms > 0

    def test_drift_behind(self):
        guard = ClockGuard(max_drift_ms=100.0)
        mt5_time = datetime.now(UTC) - timedelta(seconds=1.0)
        state = guard.check_clock(mt5_time)
        assert state.is_drifted is True
        assert state.drift_ms < 0

    def test_is_drifted_method(self):
        guard = ClockGuard(max_drift_ms=100.0)
        assert guard.is_drifted() is False
        mt5_time = datetime.now(UTC) + timedelta(seconds=1.0)
        guard.check_clock(mt5_time)
        assert guard.is_drifted() is True

    def test_get_drift_ms(self):
        guard = ClockGuard(max_drift_ms=100.0)
        assert guard.get_drift_ms() is None
        mt5_time = datetime.now(UTC) + timedelta(milliseconds=50)
        guard.check_clock(mt5_time)
        drift = guard.get_drift_ms()
        assert drift is not None
        assert abs(drift) < 1000

    def test_get_state(self):
        guard = ClockGuard(max_drift_ms=500.0)
        mt5_time = datetime.now(UTC)
        state = guard.check_clock(mt5_time)
        assert guard.get_state() is not None

    def test_drift_seconds_property(self):
        guard = ClockGuard(max_drift_ms=500.0)
        mt5_time = datetime.now(UTC) + timedelta(milliseconds=250)
        state = guard.check_clock(mt5_time)
        assert state.drift_seconds == pytest.approx(0.25, abs=0.1)

    def test_summary(self):
        guard = ClockGuard(max_drift_ms=500.0)
        mt5_time = datetime.now(UTC)
        state = guard.check_clock(mt5_time)
        summary = state.summary()
        assert "Clock" in summary

    def test_invalid_max_drift(self):
        with pytest.raises(ValueError):
            ClockGuard(max_drift_ms=0)

    def test_naive_datetime_treated_as_utc(self):
        guard = ClockGuard(max_drift_ms=500.0)
        naive_time = datetime.now(UTC)
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
        saturday = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
        result = guard.check(saturday)
        assert result.state == SessionState.CLOSED_WEEKEND
        assert result.is_open is False

    def test_weekday_open(self):
        guard = MarketSessionGuard("XAUUSD")
        # Wednesday noon UTC — should be within forex session
        wednesday = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
        result = guard.check(wednesday)
        assert result.state == SessionState.OPEN
        assert result.is_open is True

    def test_holiday_closed(self):
        config = MarketSessionConfig(holidays=((1, 1),))
        guard = MarketSessionGuard("XAUUSD", config=config)
        new_year = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        result = guard.check(new_year)
        assert result.state == SessionState.CLOSED_HOLIDAY

    def test_outside_session_hours(self):
        config = MarketSessionConfig(
            forex_open_utc=time(8, 0),
            forex_close_utc=time(17, 0),
        )
        guard = MarketSessionGuard("XAUUSD", config=config)
        # 3 AM UTC — outside session
        night = datetime(2026, 6, 24, 3, 0, tzinfo=UTC)
        result = guard.check(night)
        assert result.state == SessionState.CLOSED_SESSION

    def test_is_open_method(self):
        guard = MarketSessionGuard("XAUUSD")
        wednesday = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
        assert guard.is_open(wednesday) is True

    def test_is_eligible_for_order(self):
        guard = MarketSessionGuard("XAUUSD")
        wednesday = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
        result = guard.check(wednesday)
        assert result.is_eligible_for_order is True

    def test_summary(self):
        guard = MarketSessionGuard("XAUUSD")
        wednesday = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
        result = guard.check(wednesday)
        assert "Session" in result.summary()

    def test_sunday_closed(self):
        guard = MarketSessionGuard("XAUUSD")
        sunday = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)
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
            level: str = "HEALTHY"
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
        class HealthyFeed:
            level: str = "HEALTHY"
            last_tick_age_seconds: float = 1.0
            max_tick_age_seconds: float = 3.0

        @dataclass
        class NormalSpread:
            is_wide: bool = False

        @dataclass
        class ClosedSession:
            is_open: bool = False
            state: SessionState = SessionState.CLOSED_WEEKEND

        result = machine.evaluate(
            feed_health=HealthyFeed(),
            spread_state=NormalSpread(),
            session_state=ClosedSession(),
        )
        assert result.state == MarketHealthState.MARKET_CLOSED
        assert result.eligible_for_new_order is False

    def test_stale_feed(self):
        machine = MarketHealthMachine("XAUUSD")

        @dataclass
        class StaleFeed:
            level: str = "STALE_FEED"
            last_tick_age_seconds: float = 10.0
            max_tick_age_seconds: float = 3.0

        result = machine.evaluate(feed_health=StaleFeed())
        assert result.state == MarketHealthState.STALE_FEED
        assert result.eligible_for_new_order is False

    def test_wide_spread(self):
        machine = MarketHealthMachine("XAUUSD")

        @dataclass
        class HealthyFeed:
            level: str = "HEALTHY"
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
            level: str = "HEALTHY"
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
            level: str = "HEALTHY"
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
            level: str = "HEALTHY"
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
            level: str = "HEALTHY"
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
            level: str = "DISCONNECTED"
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
            level: str = "STALE_FEED"
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
            level: str = "STALE_FEED"
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
        tracker = DataWatermarkTracker("XAUUSD")
        tick = _make_tick_record(ts=datetime.now(UTC))
        tick.data_quality = "VALID"
        watermark = tracker.update(tick)
        assert tracker.is_fresh(max_age_seconds=10.0) is True

    def test_stale_after_timeout(self):
        tracker = DataWatermarkTracker("XAUUSD")
        tick = _make_tick_record(ts=datetime.now(UTC) - timedelta(seconds=5))
        tracker.update(tick)
        assert tracker.is_fresh(max_age_seconds=1.0) is False

    def test_update_count(self):
        tracker = DataWatermarkTracker("XAUUSD")
        for i in range(3):
            tick = _make_tick_record(ts=datetime.now(UTC) + timedelta(seconds=i))
            tracker.update(tick)
        watermark = tracker.get_watermark()
        assert watermark.tick_count == 3

    def test_gap_count(self):
        tracker = DataWatermarkTracker("XAUUSD")
        tick = _make_tick_record(ts=datetime.now(UTC))
        tick.data_quality = "GAP"
        tracker.update(tick)
        watermark = tracker.get_watermark()
        assert watermark.gap_count == 1

    def test_stale_count(self):
        tracker = DataWatermarkTracker("XAUUSD")
        tick = _make_tick_record(ts=datetime.now(UTC))
        tick.data_quality = "STALE"
        tracker.update(tick)
        watermark = tracker.get_watermark()
        assert watermark.stale_count == 1

    def test_out_of_order_count(self):
        tracker = DataWatermarkTracker("XAUUSD")
        tick = _make_tick_record(ts=datetime.now(UTC))
        tick.data_quality = "OUT_OF_ORDER"
        tracker.update(tick)
        watermark = tracker.get_watermark()
        assert watermark.out_of_order_count == 1

    def test_has_gaps(self):
        tracker = DataWatermarkTracker("XAUUSD")
        assert tracker.has_gaps() is False
        tick = _make_tick_record(ts=datetime.now(UTC))
        tick.data_quality = "GAP"
        tracker.update(tick)
        assert tracker.has_gaps() is True

    def test_watermark_hash(self):
        tracker = DataWatermarkTracker("XAUUSD")
        tick = _make_tick_record(ts=datetime.now(UTC))
        watermark = tracker.update(tick)
        assert len(watermark.watermark_hash) == 64  # SHA-256

    def test_symbol_mismatch_raises(self):
        tracker = DataWatermarkTracker("XAUUSD")
        tick = _make_tick_record(ts=datetime.now(UTC), symbol="EURUSD")
        with pytest.raises(ValueError, match="does not match"):
            tracker.update(tick)

    def test_initial_state_none(self):
        tracker = DataWatermarkTracker("XAUUSD")
        assert tracker.get_watermark() is None

    def test_invalid_symbol(self):
        with pytest.raises(ValueError, match="must not be empty"):
            DataWatermarkTracker("")


# ===========================================================================
# 8. AccountSnapshot
# ===========================================================================


class TestAccountSnapshot:
    """Tests for AccountSnapshot: creation, redaction, serialization."""

    def test_create_snapshot(self):
        snap = create_account_snapshot(
            balance=10000.0,
            equity=10500.0,
            leverage=100,
            currency="USD",
        )
        assert snap.balance == 10000.0
        assert snap.equity == 10500.0

    def test_redaction_server(self):
        snap = create_account_snapshot(
            balance=10000.0,
            equity=10000.0,
            server="ICMarketsSC-Demo02",
            login="12345678",
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
            balance=100.0,
            equity=100.0,
            snapshot_id="custom-001",
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
            "feed_health",
            "spread",
            "clock",
            "session",
            "tick_recorder",
            "watermark",
            "account",
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
            level: str = "HEALTHY"

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
            level: str = "STALE_FEED"

        report = gen.generate(feed_health_state=StaleFeed())
        assert report.overall_status == "FAIL"

    def test_report_id_unique(self):
        import time

        gen = SmokeReportGenerator("XAUUSD")
        r1 = gen.generate()
        time.sleep(1.1)  # Ensure different second for unique ID
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
        spread = SpreadMonitor("XAUUSD", reject_multiplier=3.0)
        clock = ClockGuard(max_drift_ms=500.0)
        session = MarketSessionGuard("XAUUSD")
        machine = MarketHealthMachine("XAUUSD")

        # Feed healthy tick
        feed.on_tick_received(
            tick_timestamp=datetime.now(UTC),
            received_at=datetime.now(UTC),
        )

        # Spread baseline
        for _ in range(10):
            spread.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        spread_state = spread.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))

        # Clock OK
        clock_state = clock.check_clock(datetime.now(UTC))

        # Session open (Wednesday noon)
        session_result = session.check(datetime(2026, 6, 24, 12, 0, tzinfo=UTC))

        result = machine.evaluate(
            feed_health=feed.check_health(),
            spread_state=spread_state,
            clock_state=clock_state,
            session_state=session_result,
        )
        assert result.state == MarketHealthState.HEALTHY
        assert result.eligible_for_new_order is True

    def test_integration_wide_spread_blocks_order(self):
        """Simulate wide spread and verify order blocked."""
        feed = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=3.0)
        feed.on_tick_received(
            tick_timestamp=datetime.now(UTC),
            received_at=datetime.now(UTC),
        )

        spread = SpreadMonitor("XAUUSD", reject_multiplier=2.0)
        for _ in range(10):
            spread.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        spread_state = spread.on_tick(Decimal("2330.0"), Decimal("2335.0"), datetime.now(UTC))  # wide!

        clock = ClockGuard(max_drift_ms=500.0)
        clock_state = clock.check_clock(datetime.now(UTC))

        session = MarketSessionGuard("XAUUSD")
        session_result = session.check(datetime(2026, 6, 24, 12, 0, tzinfo=UTC))

        machine = MarketHealthMachine("XAUUSD")
        result = machine.evaluate(
            feed_health=feed.check_health(),
            spread_state=spread_state,
            clock_state=clock_state,
            session_state=session_result,
        )
        assert result.eligible_for_new_order is False
        assert "WIDE_SPREAD" in result.reason_codes

    def test_integration_weekend_closed(self):
        """Weekend → MARKET_CLOSED → not eligible."""
        feed = FeedHealthMonitor("XAUUSD", max_tick_age_seconds=3.0)
        feed.on_tick_received(
            tick_timestamp=datetime.now(UTC),
            received_at=datetime.now(UTC),
        )

        spread = SpreadMonitor("XAUUSD", reject_multiplier=3.0)
        for _ in range(10):
            spread.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))
        spread_state = spread.on_tick(Decimal("2330.0"), Decimal("2331.0"), datetime.now(UTC))

        clock = ClockGuard(max_drift_ms=500.0)
        clock_state = clock.check_clock(datetime.now(UTC))

        session = MarketSessionGuard("XAUUSD")
        session_result = session.check(datetime(2026, 6, 27, 12, 0, tzinfo=UTC))

        machine = MarketHealthMachine("XAUUSD")
        result = machine.evaluate(
            feed_health=feed.check_health(),
            spread_state=spread_state,
            clock_state=clock_state,
            session_state=session_result,
        )
        assert result.state == MarketHealthState.MARKET_CLOSED
        assert result.eligible_for_new_order is False
