"""Phase 5 — Bootstrap sensitivity analysis tests."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from validation.bootstrap_sensitivity import bootstrap_confidence_interval


def test_bootstrap_deterministic():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    r1 = bootstrap_confidence_interval(values, seed=42)
    r2 = bootstrap_confidence_interval(values, seed=42)
    assert r1.observed_value == r2.observed_value
    assert r1.confidence_interval_95 == r2.confidence_interval_95
    assert r1.n_resamples == r2.n_resamples


def test_bootstrap_positive_values():
    values = [0.5, 1.0, 1.5, 2.0, 2.5]
    result = bootstrap_confidence_interval(values)
    assert result.observed_value == 1.5
    assert result.passes_threshold is True
    assert result.confidence_interval_95[0] > 0


def test_bootstrap_negative_values():
    values = [-2.0, -1.5, -1.0, -0.5]
    result = bootstrap_confidence_interval(values)
    assert result.passes_threshold is False
    assert result.confidence_interval_95[1] < 0


def test_bootstrap_empty_values():
    result = bootstrap_confidence_interval([])
    assert result.observed_value == 0
    assert result.confidence_interval_95 == (0, 0)
    assert result.passes_threshold is False
    assert result.n_resamples == 0


def test_bootstrap_confidence_interval_width():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    narrow = bootstrap_confidence_interval(values, n_resamples=100)
    wide = bootstrap_confidence_interval(values, n_resamples=10000)
    ci_narrow = narrow.confidence_interval_95[1] - narrow.confidence_interval_95[0]
    ci_wide = wide.confidence_interval_95[1] - wide.confidence_interval_95[0]
    assert ci_wide <= ci_narrow * 1.5  # more resamples → similar or tighter CI
