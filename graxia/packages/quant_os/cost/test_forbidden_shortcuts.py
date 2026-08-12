"""Tests for forbidden shortcuts guard."""
from graxia.packages.quant_os.cost.forbidden_shortcuts import ForbiddenShortcutsGuard


def test_guard_allows_valid():
    guard = ForbiddenShortcutsGuard()
    ok, msg = guard.check("quote_observed_calibration")
    assert ok
    assert guard.is_clean()


def test_guard_rejects_forbidden():
    guard = ForbiddenShortcutsGuard()
    ok, msg = guard.check("random_normal_slippage")
    assert not ok
    assert "forbidden" in msg
    assert not guard.is_clean()


def test_guard_check_all():
    guard = ForbiddenShortcutsGuard()
    ok, issues = guard.check_all([
        "quote_observed_calibration",
        "random_normal_slippage",
        "demo_fills_as_live_proof",
    ])
    assert not ok
    assert len(issues) == 2


def test_guard_all_forbidden():
    guard = ForbiddenShortcutsGuard()
    for shortcut in ["random_normal_slippage", "queue_position_without_depth",
                      "demo_fills_as_live_proof"]:
        ok, _ = guard.check(shortcut)
        assert not ok
    assert len(guard.get_violations()) == 3
