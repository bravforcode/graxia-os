"""Regression tests for dsr_from_annualized (SP1: DSR unit correctness)."""

import importlib.util
import math
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("deflated_sharpe", str(_ROOT / "validation" / "deflated_sharpe.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
dsr_from_annualized = _mod.dsr_from_annualized
deflated_sharpe_ratio = _mod.deflated_sharpe_ratio


def test_trial_1032_scenario_fails_with_correct_factor():
    """SR=0.34 annualized, N=1050, N_obs=5392, daily bars -> must FAIL (p~0.955).
    This is the exact trial 1032 numbers that falsely PASSed with factor=1.0."""
    r = dsr_from_annualized(0.34, 1050, 5392, annualization_factor=252)
    assert not r.passes_threshold
    assert r.probability_alpha > 0.90  # ~0.955


def test_high_sharpe_passes():
    """SR=2.0 annualized must PASS at N=1050."""
    r = dsr_from_annualized(2.0, 1050, 5392, annualization_factor=252)
    assert r.passes_threshold


def test_annualization_factor_affects_result():
    """H1 (6096 bars/yr) must differ from D1 (252) — proves factor is not hardcoded."""
    r_d1 = dsr_from_annualized(1.0, 1050, 5392, annualization_factor=252)
    r_h1 = dsr_from_annualized(1.0, 1050, 5392, annualization_factor=6096)
    assert r_h1.probability_alpha > r_d1.probability_alpha


def test_kurtosis_raw_convention():
    """Helper must treat kurtosis as RAW (3=normal). Excess kurtosis (0) must differ.

    SR is kept moderate (0.8): at extreme SR with N_obs=5000 the erf-based CDF
    saturates probability_alpha to 0.0 for any kurtosis, masking the difference.
    """
    r_raw = dsr_from_annualized(0.8, 50, 5000, annualization_factor=252, kurtosis=3.0)
    r_excess = dsr_from_annualized(0.8, 50, 5000, annualization_factor=252, kurtosis=0.0)
    assert r_raw.probability_alpha != r_excess.probability_alpha


def test_single_trial_not_overpenalized():
    """n_trials=1 (no multiple testing) must not crash and must be less conservative."""
    r = dsr_from_annualized(1.5, 1, 5000, annualization_factor=252)
    assert r.passes_threshold  # no multiplicity penalty with N=1


def test_equivalence_with_direct_call():
    """dsr_from_annualized(f) == deflated_sharpe_ratio(factor=sqrt(f))."""
    r1 = dsr_from_annualized(1.2, 100, 3000, annualization_factor=252, skewness=0.1, kurtosis=3.5)
    r2 = deflated_sharpe_ratio(1.2, 100, 3000, sharpe_annualization_factor=math.sqrt(252), skewness=0.1, kurtosis=3.5)
    assert r1.probability_alpha == r2.probability_alpha
    assert r1.passes_threshold == r2.passes_threshold
