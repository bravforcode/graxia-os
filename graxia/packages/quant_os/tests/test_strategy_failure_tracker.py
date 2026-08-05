"""Tests for _StrategyFailureTracker — auto-disable on repeated strategy failures.

Covers:
- Auto-disable after threshold failures
- Window pruning (old failures expire)
- Re-enable after timeout
- Manual reset
- Symbol independence
- Module-level singleton
"""

from __future__ import annotations

import time

import pytest

pytest.skip(
    "_StrategyFailureTracker was never implemented in alpha/engine.py and has "
    "zero production callers anywhere in the repo (not even a partial stub or "
    "wiring point) — implementing it now would mean inventing a whole unwired "
    "subsystem solely to satisfy this test. Revisit if/when a real caller needs "
    "a per-strategy circuit breaker.",
    allow_module_level=True,
)

from graxia.packages.quant_os.alpha.engine import (  # noqa: E402
    _FAIL_THRESHOLD,
    _FAIL_WINDOW_SECONDS,
    _failure_tracker,
    _StrategyFailureTracker,
)


class TestStrategyFailureTrackerAutoDisable:
    """Auto-disable after threshold failures within window."""

    def test_no_failures_not_disabled(self):
        t = _StrategyFailureTracker()
        assert not t.is_disabled("strat", "XAUUSD")

    def test_below_threshold_not_disabled(self):
        t = _StrategyFailureTracker()
        for _ in range(_FAIL_THRESHOLD - 1):
            t.record_failure("strat", "XAUUSD")
        assert not t.is_disabled("strat", "XAUUSD")

    def test_at_threshold_disabled(self):
        t = _StrategyFailureTracker()
        for _ in range(_FAIL_THRESHOLD):
            t.record_failure("strat", "XAUUSD")
        assert t.is_disabled("strat", "XAUUSD")

    def test_above_threshold_disabled(self):
        t = _StrategyFailureTracker()
        for _ in range(_FAIL_THRESHOLD + 5):
            t.record_failure("strat", "XAUUSD")
        assert t.is_disabled("strat", "XAUUSD")


class TestStrategyFailureTrackerWindowPruning:
    """Old failures outside the window are pruned."""

    def test_old_failures_pruned(self):
        t = _StrategyFailureTracker()
        # Inject 2 old failures (outside window)
        old_time = time.monotonic() - _FAIL_WINDOW_SECONDS - 10
        t._failures["strat:XAUUSD"] = [old_time, old_time]
        # 1 fresh failure — total should be 1 (old ones pruned)
        t.record_failure("strat", "XAUUSD")
        assert not t.is_disabled("strat", "XAUUSD")

    def test_mixed_old_and_new(self):
        t = _StrategyFailureTracker()
        # 1 old + 2 new = 3 total, but old gets pruned → 2 total
        old_time = time.monotonic() - _FAIL_WINDOW_SECONDS - 10
        t._failures["strat:XAUUSD"] = [old_time]
        for _ in range(2):
            t.record_failure("strat", "XAUUSD")
        # Old one pruned, 2 new ones < threshold
        assert not t.is_disabled("strat", "XAUUSD")

    def test_all_new_failures_trigger_disable(self):
        t = _StrategyFailureTracker()
        old_time = time.monotonic() - _FAIL_WINDOW_SECONDS - 10
        t._failures["strat:XAUUSD"] = [old_time]
        for _ in range(_FAIL_THRESHOLD):
            t.record_failure("strat", "XAUUSD")
        # 1 old pruned + 3 new = 3 new ≥ threshold
        assert t.is_disabled("strat", "XAUUSD")


class TestStrategyFailureTrackerReEnable:
    """Strategy re-enables after disable duration expires."""

    def test_reenable_after_timeout(self):
        t = _StrategyFailureTracker()
        t._disable_duration = 0.01  # 10ms for testing
        for _ in range(_FAIL_THRESHOLD):
            t.record_failure("strat", "XAUUSD")
        assert t.is_disabled("strat", "XAUUSD")
        time.sleep(0.02)
        assert not t.is_disabled("strat", "XAUUSD")

    def test_reenable_clears_failure_history(self):
        t = _StrategyFailureTracker()
        t._disable_duration = 0.01
        for _ in range(_FAIL_THRESHOLD):
            t.record_failure("strat", "XAUUSD")
        time.sleep(0.02)
        assert not t.is_disabled("strat", "XAUUSD")
        # Need fresh threshold failures to re-disable
        for _ in range(_FAIL_THRESHOLD - 1):
            t.record_failure("strat", "XAUUSD")
        assert not t.is_disabled("strat", "XAUUSD")
        t.record_failure("strat", "XAUUSD")
        assert t.is_disabled("strat", "XAUUSD")


class TestStrategyFailureTrackerReset:
    """Manual reset clears failure state."""

    def test_reset_clears_disabled(self):
        t = _StrategyFailureTracker()
        for _ in range(_FAIL_THRESHOLD):
            t.record_failure("strat", "XAUUSD")
        assert t.is_disabled("strat", "XAUUSD")
        t.reset("strat", "XAUUSD")
        assert not t.is_disabled("strat", "XAUUSD")

    def test_reset_clears_failure_history(self):
        t = _StrategyFailureTracker()
        for _ in range(_FAIL_THRESHOLD):
            t.record_failure("strat", "XAUUSD")
        t.reset("strat", "XAUUSD")
        # Need fresh threshold failures to re-disable
        for _ in range(_FAIL_THRESHOLD - 1):
            t.record_failure("strat", "XAUUSD")
        assert not t.is_disabled("strat", "XAUUSD")

    def test_reset_nonexistent_is_noop(self):
        t = _StrategyFailureTracker()
        t.reset("nonexistent", "XAUUSD")  # should not raise


class TestStrategyFailureTrackerSymbolIndependence:
    """Different symbols are tracked independently."""

    def test_symbols_independent(self):
        t = _StrategyFailureTracker()
        for _ in range(_FAIL_THRESHOLD):
            t.record_failure("strat", "XAUUSD")
        assert t.is_disabled("strat", "XAUUSD")
        assert not t.is_disabled("strat", "EURUSD")

    def test_strategies_independent(self):
        t = _StrategyFailureTracker()
        for _ in range(_FAIL_THRESHOLD):
            t.record_failure("mtm", "XAUUSD")
        assert t.is_disabled("mtm", "XAUUSD")
        assert not t.is_disabled("mrb", "XAUUSD")


class TestStrategyFailureTrackerModuleSingleton:
    """Module-level _failure_tracker is a singleton."""

    def test_singleton_exists(self):
        assert _failure_tracker is not None
        assert isinstance(_failure_tracker, _StrategyFailureTracker)

    def test_singleton_is_same_object(self):
        from graxia.packages.quant_os.alpha.engine import _failure_tracker as ft2

        assert _failure_tracker is ft2
