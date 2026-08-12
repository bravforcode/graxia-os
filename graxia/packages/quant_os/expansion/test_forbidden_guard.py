"""Tests for forbidden expansion guard."""
from graxia.packages.quant_os.expansion.forbidden_guard import ForbiddenExpansionGuard


def test_guard_allows_valid():
    guard = ForbiddenExpansionGuard()
    ok, violations = guard.check("add one more strategy")
    assert ok


def test_guard_rejects_win_streak():
    guard = ForbiddenExpansionGuard()
    ok, violations = guard.check("raising risk on win streak")
    assert not ok
    assert len(violations) == 1


def test_guard_rejects_crypto():
    guard = ForbiddenExpansionGuard()
    ok, violations = guard.check("mixing crypto and fx")
    assert not ok


def test_guard_rejects_xauusd():
    guard = ForbiddenExpansionGuard()
    ok, violations = guard.check("using xauusd strategy on eurusd")
    assert not ok
