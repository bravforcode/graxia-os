"""Tests for anti-contamination guard."""
from graxia.packages.quant_os.markets.eurusd.anti_contamination import AntiContaminationGuard


def test_guard_allows_same_market():
    guard = AntiContaminationGuard()
    check = guard.check_transfer("EURUSD", "EURUSD", "threshold_1")
    assert not check.is_contaminated
    assert guard.is_clean()


def test_guard_blocks_xauusd_to_eurusd():
    guard = AntiContaminationGuard()
    check = guard.check_transfer("XAUUSD", "EURUSD", "threshold_1")
    assert check.is_contaminated
    assert not guard.is_clean()


def test_guard_allows_hypothesis_transfer():
    guard = AntiContaminationGuard()
    check = guard.check_transfer("XAUUSD", "EURUSD", "hypothesis_new")
    assert not check.is_contaminated


def test_guard_violations_tracked():
    guard = AntiContaminationGuard()
    guard.check_transfer("XAUUSD", "EURUSD", "param_1")
    guard.check_transfer("XAUUSD", "EURUSD", "param_2")
    assert len(guard.get_violations()) == 2
