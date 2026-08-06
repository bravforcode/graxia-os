# tests/test_screening_guard.py
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from screening_guard import GuardViolationError, assert_no_guard_violations, attr_scan


class FakeGuard:
    def __init__(self, violations):
        self.violations = violations


class FakeEngine:
    def __init__(self, violations=None, has_guard=True):
        self.guard = FakeGuard(violations or []) if has_guard else None


class FakeStrategy:
    def __init__(self):
        self.bars = 100


def test_no_violations_passes():
    assert_no_guard_violations(FakeEngine([]), config_id="c1")


def test_violations_raise():
    with pytest.raises(GuardViolationError, match="c1"):
        assert_no_guard_violations(FakeEngine(["leak@bar 5"]), config_id="c1")


def test_missing_guard_raises_fail_closed():
    # review finding #3: engine without .guard must NOT pass silently
    with pytest.raises(GuardViolationError, match="no .guard"):
        assert_no_guard_violations(FakeEngine(has_guard=False), config_id="c2")


def test_attr_scan_clean():
    s = FakeStrategy()
    before = dict(vars(s))
    assert attr_scan(s, before) == []


def test_attr_scan_detects_mutation():
    s = FakeStrategy()
    before = dict(vars(s))
    s.bars = 999
    mutated = attr_scan(s, before)
    assert "bars" in mutated


def test_attr_scan_detects_added_attribute():
    # review finding #4: attributes ADDED mid-run (leak pattern) must be visible
    s = FakeStrategy()
    before = dict(vars(s))
    s.hidden_future_bars = [1, 2, 3]
    mutated = attr_scan(s, before)
    assert "hidden_future_bars" in mutated
