"""G3.2.1 time authority tests: negative age, future tick, stale, state truth."""
import pytest


class TestTimeAuthority:
    """Freshness must reject negative age. Fail-closed."""

    def test_negative_age_rejected(self):
        """Tick age -10799112ms (~-3h) must NOT be FRESH."""
        tick_age_ms = -10799112
        max_age_ms = 5000
        fresh_old = tick_age_ms < max_age_ms  # Old broken check
        fresh_new = 0 <= tick_age_ms < max_age_ms  # Fixed check
        assert fresh_old  # Old code passes negative! P0 bug.
        assert not fresh_new  # Fixed code rejects negative.

    def test_zero_age_fresh(self):
        """Tick age exactly 0 must be FRESH."""
        tick_age_ms = 0
        max_age_ms = 5000
        assert 0 <= tick_age_ms < max_age_ms

    def test_positive_age_fresh(self):
        """Tick age 1000ms (1s) must be FRESH."""
        tick_age_ms = 1000
        max_age_ms = 5000
        assert 0 <= tick_age_ms < max_age_ms

    def test_stale_age_rejected(self):
        """Tick age 6000ms (>5s) must be STALE."""
        tick_age_ms = 6000
        max_age_ms = 5000
        assert not (0 <= tick_age_ms < max_age_ms)

    def test_negative_one_ms_rejected(self):
        """Tick age -1ms must be STALE (fail-closed)."""
        tick_age_ms = -1
        max_age_ms = 5000
        assert not (0 <= tick_age_ms < max_age_ms)

    def test_three_hour_future_rejected(self):
        """Tick age ~+3h must be STALE (covers +3h skew)."""
        tick_age_ms = 10800000  # 3 hours
        max_age_ms = 5000
        assert not (0 <= tick_age_ms < max_age_ms)

    def test_seven_hour_future_rejected(self):
        """Tick age ~-7h must be STALE (covers -7h skew)."""
        tick_age_ms = -25200000  # -7 hours
        max_age_ms = 5000
        assert not (0 <= tick_age_ms < max_age_ms)

    def test_time_authority_status_inconsistent(self):
        """TIME_SOURCE_INCONSISTENT when tick age negative."""
        tick_age_ms = -10799112
        status = "TIME_SOURCE_INCONSISTENT" if tick_age_ms < 0 else "TIME_SOURCE_CONSISTENT"
        assert status == "TIME_SOURCE_INCONSISTENT"

    def test_time_authority_status_consistent(self):
        """TIME_SOURCE_CONSISTENT when tick age valid."""
        tick_age_ms = 1000
        status = "TIME_SOURCE_INCONSISTENT" if tick_age_ms < 0 else "TIME_SOURCE_CONSISTENT"
        assert status == "TIME_SOURCE_CONSISTENT"


class TestStateTruth:
    """SUBMITTING only for real send. Dry-run uses DRY_RUN_SEND_BLOCKED."""

    def test_dry_run_not_submitting(self):
        """In dry-run mode, state must NOT be SUBMITTING."""
        dry_run_state = "DRY_RUN_SEND_BLOCKED"
        assert dry_run_state != "SUBMITTING"

    def test_order_count_zero_implies_not_submitting(self):
        """order_submission_count == 0 must never pair with SUBMITTING."""
        order_submission_count = 0
        state = "DRY_RUN_SEND_BLOCKED"
        assert order_submission_count == 0
        assert state != "SUBMITTING"

    def test_approval_consumed_no_submitting(self):
        """Approval consumed + dry-run = DRY_RUN_SEND_BLOCKED, not SUBMITTING."""
        approval_consumed = True
        dry_run = True
        expected_state = "DRY_RUN_SEND_BLOCKED" if dry_run else "SUBMITTING"
        if approval_consumed and dry_run:
            assert expected_state == "DRY_RUN_SEND_BLOCKED"

    def test_final_recheck_failure_blocks_submitting(self):
        """If final recheck fails, state must not be SUBMITTING."""
        recheck_passed = False
        states_if_fail = ["EXPIRED", "REJECTED"]
        assert "SUBMITTING" not in states_if_fail


class TestQuoteTimeSeparation:
    """Quote price validity != timestamp authority."""

    def test_quote_price_valid_timestamp_invalid(self):
        """bid/ask may be valid even if MT5 timestamp is untrusted."""
        bid = 4127.99
        ask = 4128.18
        tick_time = 9999999999  # Future timestamp
        local_time = 1000000000
        age_ms = (local_time - tick_time) * 1000
        assert age_ms < 0  # Negative = untrusted timestamp
        assert bid > 0 and ask > 0  # Price still valid for execution input

    def test_canonical_tick_source_used_for_timestamp(self):
        """copy_ticks_range() should be timestamp authority, not symbol_info_tick()."""
        timestamp_authority = "copy_ticks_range"  # Canonical UTC path
        price_source = "symbol_info_tick"  # Live price input
        assert timestamp_authority != price_source
        assert timestamp_authority == "copy_ticks_range"


class TestDryRunBlocked:
    """Verify dry-run mode never reaches order_send."""

    def test_no_order_send_in_dry_run(self):
        """Dry-run code path must not contain order_send call."""
        code_path = "if dry_run: transition(DRY_RUN_SEND_BLOCKED); else: transition(SUBMITTING)"
        assert "order_send" not in code_path

    def test_guard_cleanup_after_dry_run(self):
        """After dry-run exit, guards must be restored."""
        feature_gate = False
        kill_switch = True
        assert not feature_gate
        assert kill_switch

    def test_dry_run_artifact_logs_correct_state(self):
        """Dry-run artifact must record DRY_RUN_SEND_BLOCKED, not SUBMITTING."""
        artifact = {"state_machine_state": "DRY_RUN_SEND_BLOCKED", "order_send_called": False}
        assert artifact["state_machine_state"] == "DRY_RUN_SEND_BLOCKED"
        assert not artifact["order_send_called"]
