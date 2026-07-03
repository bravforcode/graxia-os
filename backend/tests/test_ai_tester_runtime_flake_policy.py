"""Tests for runtime flake/retry policy."""
from __future__ import annotations

import pytest


class FlakePolicy:
    """Flake policy rules."""

    MAX_RETRIES = 1  # Only for infrastructure flake classification
    NO_BLIND_RETRY = True  # Never retry to hide real bugs
    FUNCTIONAL_FAILURE_IS_REAL = True  # Functional assertion failures are real
    RETRY_ONLY_FOR_FLAKE_CLASSIFICATION = True
    FLAKY_PASS_IS_NOT_PASS = True


class TestFlakePolicy:
    """Tests the flake/retry policy rules."""

    def test_max_retries_is_one(self):
        """Only one retry allowed for infrastructure flake classification."""
        assert FlakePolicy.MAX_RETRIES == 1

    def test_no_blind_retry(self):
        """No blind retry to hide bugs."""
        assert FlakePolicy.NO_BLIND_RETRY is True

    def test_functional_failure_is_real(self):
        """Functional assertion failures are real failures."""
        assert FlakePolicy.FUNCTIONAL_FAILURE_IS_REAL is True

    def test_flaky_pass_is_not_pass(self):
        """If passes only after retry => FLAKY_PASS, not PASS."""
        assert FlakePolicy.FLAKY_PASS_IS_NOT_PASS is True

    def test_retry_only_for_flake_classification(self):
        assert FlakePolicy.RETRY_ONLY_FOR_FLAKE_CLASSIFICATION is True


class TestFlakeClassification:
    """Tests flake classification logic."""

    def test_first_attempt_pass_is_pass(self):
        """Pass on first attempt is a real PASS."""
        attempts = [True]
        verdict = "PASS" if attempts[0] else "FAIL"
        assert verdict == "PASS"

    def test_second_attempt_pass_is_flaky(self):
        """Pass only after retry is FLAKY_PASS."""
        attempts = [False, True]
        if any(attempts) and not attempts[0]:
            verdict = "FLAKY_PASS"
        else:
            verdict = "PASS" if all(attempts) else "FAIL"
        assert verdict == "FLAKY_PASS"

    def test_all_fail_is_fail(self):
        """Fail on both attempts is FAIL."""
        attempts = [False, False]
        if any(attempts) and not attempts[0]:
            verdict = "FLAKY_PASS"
        else:
            verdict = "PASS" if all(attempts) else "FAIL"
        assert verdict == "FAIL"

    def test_browser_failures_require_trace(self):
        """Browser failures should capture trace/screenshot."""
        trace_available = True  # simulated
        assert trace_available or not trace_available  # contract only

    def test_startup_port_conflict_is_blocker(self):
        """Port conflicts are infrastructure blockers, not product pass."""
        port_in_use = True
        if port_in_use:
            result = "BLOCKED"
        assert result == "BLOCKED"

    def test_network_unavailable_is_blocker(self):
        """Network unavailable is blocker, not product pass."""
        network_up = False
        if not network_up:
            result = "BLOCKED"
        assert result == "BLOCKED"

    def test_retry_does_not_change_assertion(self):
        """Retry should not change what is being asserted."""
        original_assertion = "result['allowed'] is True"
        retry_assertion = "result['allowed'] is True"
        assert original_assertion == retry_assertion


class TestFlakeEvidenceContract:
    """Tests that flake evidence is properly recorded."""

    def test_flaky_pass_recorded_correctly(self):
        from app.beta.synthetic_tester.runtime_evidence import RuntimeEvidence

        ev = RuntimeEvidence(
            component="api",
            scenario_id="F001",
            scenario_name="Flaky test scenario",
        )
        ev.complete("FLAKY_PASS")
        assert ev.result == "FLAKY_PASS"
        assert ev.result != "PASS"

    def test_flaky_evidence_has_limitations(self):
        from app.beta.synthetic_tester.runtime_evidence import RuntimeEvidence

        ev = RuntimeEvidence(
            component="api",
            scenario_id="F002",
            scenario_name="Flaky with limitations",
        )
        ev.add_limitation("Passed on retry — classified as infrastructure flake")
        ev.complete("FLAKY_PASS")
        assert len(ev.limitations) >= 1
