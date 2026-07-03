"""BE-P8.3.2 — Time source consistency guards.

Tests the 4 temporal-consistency rules.
"""

from datetime import UTC, datetime

from graxia.packages.quant_os.shadow.time_source_reconciler import (
    CycleEvidence,
    SealedLedger,
    TimeConsistencyResult,
    check_rule_a,
    check_rule_b,
    check_rule_c,
)

# ── Rule A: tick within ±60s of received_at ──────────────────────────


class TestRuleA:
    def test_tick_matching_received(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        tick = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        passed, diff = check_rule_a(tick, now)
        assert passed is True
        assert diff == 0.0

    def test_tick_5s_early(self):
        now = datetime(2026, 1, 1, 12, 0, 5, tzinfo=UTC)
        tick = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        passed, diff = check_rule_a(tick, now)
        assert passed is True
        assert diff == 5000.0

    def test_tick_60s_late(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        tick = datetime(2026, 1, 1, 12, 1, 0, tzinfo=UTC)
        passed, diff = check_rule_a(tick, now)
        assert passed is True
        assert diff == 60000.0

    def test_tick_61s_late_fails(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        tick = datetime(2026, 1, 1, 12, 1, 1, tzinfo=UTC)
        passed, diff = check_rule_a(tick, now)
        assert passed is False

    def test_tick_3h_ahead_fails(self):
        """The actual BROKER_CLOCK_ANOMALY scenario."""
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        tick = datetime(2026, 1, 1, 15, 0, 0, tzinfo=UTC)
        passed, diff = check_rule_a(tick, now)
        assert passed is False
        assert diff == 10800000.0  # 3 hours in ms

    def test_tick_none_fails(self):
        passed, diff = check_rule_a(None, datetime.now(UTC))
        assert passed is False


# ── Rule B: ticks within requested window ────────────────────────────


class TestRuleB:
    def test_all_ticks_in_window(self):
        # Use epochs that fall within the window
        fr = datetime(2026, 6, 22, 12, 0, 0, tzinfo=UTC)
        to = datetime(2026, 6, 22, 12, 1, 0, tzinfo=UTC)
        ticks = [{"time": int(fr.timestamp()) + 10}, {"time": int(fr.timestamp()) + 50}]
        passed, outside = check_rule_b(ticks, fr, to)
        assert passed is True
        assert outside == 0

    def test_tick_outside_window(self):
        fr = datetime(2026, 6, 22, 12, 0, 0, tzinfo=UTC)
        to = datetime(2026, 6, 22, 12, 0, 30, tzinfo=UTC)
        ticks = [{"time": int(fr.timestamp()) + 10}, {"time": int(fr.timestamp()) + 120}]  # 120s outside
        passed, outside = check_rule_b(ticks, fr, to)
        assert passed is False
        assert outside == 1

    def test_no_ticks_passes(self):
        passed, outside = check_rule_b([], datetime.now(UTC), datetime.now(UTC))
        assert passed is True


# ── Rule C: bars not in future ───────────────────────────────────────


class TestRuleC:
    def test_bars_in_past(self):
        now = datetime(2026, 6, 22, 12, 0, 0, tzinfo=UTC)
        bars = [{"time": int(now.timestamp()) - 3600}]  # 1h ago
        passed, future = check_rule_c(bars, now)
        assert passed is True

    def test_bar_in_future_fails(self):
        bars = [{"time": 1782150000}]  # future
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        passed, future = check_rule_c(bars, now)
        assert passed is False
        assert future == 1

    def test_no_bars_passes(self):
        passed, future = check_rule_c([], datetime.now(UTC))
        assert passed is True


# ── Consistency verdict ──────────────────────────────────────────────


class TestConsistencyVerdict:
    def test_all_pass(self):
        r = TimeConsistencyResult(
            rule_a_tick_within_60s=True,
            rule_b_ticks_in_window=True,
            rule_c_bars_not_future=True,
        )
        assert r.evaluate() == "PASS"

    def test_rule_a_fails(self):
        r = TimeConsistencyResult(
            rule_a_tick_within_60s=False,
            rule_b_ticks_in_window=True,
            rule_c_bars_not_future=True,
        )
        assert r.evaluate() == "TIME_SOURCE_INCONSISTENT"

    def test_rule_b_fails(self):
        r = TimeConsistencyResult(
            rule_a_tick_within_60s=True,
            rule_b_ticks_in_window=False,
            rule_c_bars_not_future=True,
        )
        assert r.evaluate() == "TIME_SOURCE_INCONSISTENT"

    def test_rule_c_fails(self):
        r = TimeConsistencyResult(
            rule_a_tick_within_60s=True,
            rule_b_ticks_in_window=True,
            rule_c_bars_not_future=False,
        )
        assert r.evaluate() == "TIME_SOURCE_INCONSISTENT"


# ── Sealed ledger ────────────────────────────────────────────────────


class TestSealedLedger:
    def test_append_and_verify(self):
        ledger = SealedLedger()
        ev = CycleEvidence(cycle_id=1, system_epoch_ms=1000, tick_raw_time=1000)
        h = ledger.append(ev)
        assert len(h) == 64
        assert ledger.verify() is True

    def test_tamper_detected(self):
        ledger = SealedLedger()
        ev = CycleEvidence(cycle_id=1, system_epoch_ms=1000, tick_raw_time=1000)
        ledger.append(ev)
        ledger._entries[0]["system_epoch_ms"] = 9999  # tamper
        assert ledger.verify() is False

    def test_seal(self):
        ledger = SealedLedger()
        ev = CycleEvidence(cycle_id=1, system_epoch_ms=1000, tick_raw_time=1000)
        ledger.append(ev)
        assert len(ledger.seal()) == 64


# ── Rule A applied to real data (BROKER_CLOCK_ANOMALY) ───────────────


class TestRealDataAnomaly:
    def test_3h_offset_fails_rule_a(self):
        """From real MT5 data: tick is +3h from system."""
        system_utc = datetime(2026, 6, 22, 16, 36, 28, tzinfo=UTC)
        tick_utc = datetime(2026, 6, 22, 19, 36, 27, tzinfo=UTC)
        passed, diff = check_rule_a(tick_utc, system_utc)
        assert passed is False
        assert abs(diff - 10799000) < 1000  # ~3h in ms

    def test_copy_ticks_range_stale(self):
        """From real data: copy_ticks_range returned 09:36 UTC (stale)."""
        ticks = [{"time": 1782120987}]
        fr = datetime(2026, 6, 22, 16, 31, 28, tzinfo=UTC)
        to = datetime(2026, 6, 22, 16, 36, 28, tzinfo=UTC)
        passed, outside = check_rule_b(ticks, fr, to)
        assert passed is False  # 09:36 is outside 16:31-16:36 window
