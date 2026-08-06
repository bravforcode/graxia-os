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
    def __init__(self, violations):
        self.guard = FakeGuard(violations)


class FakeStrategy:
    def __init__(self):
        self.bars = 100


def test_no_violations_passes():
    assert_no_guard_violations(FakeEngine([]), config_id="c1")


def test_violations_raise():
    with pytest.raises(GuardViolationError, match="c1"):
        assert_no_guard_violations(FakeEngine(["leak@bar 5"]), config_id="c1")


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
