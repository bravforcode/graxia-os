"""Tests for core/stats/psi.py — the shared PSI primitive.

Pins: (1) mathematically-known edge cases, (2) delegation fidelity through
DriftMonitor: feature-drift scores produced by the monitor must equal psi()
computed independently from the same baseline statistics.
"""

from __future__ import annotations

import sys
from pathlib import Path

# quant_os/conftest.py inserts the MONOREPO root at sys.path[0], and a
# `core` package exists at that root — it would shadow quant_os/core.
# Push the quant_os root to the FRONT unconditionally (quant_os is already
# on sys.path later, so a guarded insert is a no-op and the shadow wins).
# Same self-managed sys.path pattern as tests/test_provenance.py.
_QUANT_OS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_QUANT_OS_ROOT))

import pytest  # noqa: E402

from core.stats.psi import psi  # noqa: E402


def test_psi_identical_distributions_is_zero():
    """Identical normal distributions → every bin pair has cp == bp → PSI == 0."""
    value = psi(baseline_mean=0.0, baseline_std=1.0, current_mean=0.0, current_std=1.0)
    assert value == pytest.approx(0.0, abs=1e-9)


def test_psi_shifted_distribution_is_positive():
    """A one-half-sigma shift must produce a positive PSI (KL divergence >= 0)."""
    value = psi(baseline_mean=0.0, baseline_std=1.0, current_mean=0.5, current_std=1.0)
    assert 0.1 < value < 0.5


def test_psi_zero_std_raises_like_original():
    """Zero std raises ZeroDivisionError — identical to the pre-extraction
    DriftMonitor._calculate_psi (no sigma guard in the original; callers floor
    sigma at 1e-10 before calling, see ml/drift_monitor.py lines 441/450)."""
    with pytest.raises(ZeroDivisionError):
        psi(baseline_mean=0.0, baseline_std=0.0, current_mean=0.0, current_std=0.0)


def test_psi_floored_sigma_is_finite():
    """Callers floor sigma at 1e-10; the function must stay finite for it."""
    value = psi(baseline_mean=0.0, baseline_std=1e-10, current_mean=0.0, current_std=1e-10)
    assert value == pytest.approx(0.0, abs=1e-9)


def test_drift_monitor_feature_scores_match_shared_psi(tmp_path, monkeypatch):
    """DriftMonitor._compute_feature_psi must produce exactly what psi() yields
    from the same baseline/current statistics (delegation fidelity).

    window_size=60 evicts the first 40 predictions from the current window, so
    current = last 60 values while the baseline accumulates all 100 — a
    genuinely non-zero PSI comparison."""
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))  # keep _save_state out of data/
    from ml.drift_monitor import DriftMonitor

    monitor = DriftMonitor(state_dir=tmp_path, window_size=60)
    baseline_vals = [0.0 + 0.1 * i for i in range(40)]  # first 40 → baseline, evicted from window
    current_vals = [0.8 + 0.1 * i for i in range(60)]  # next 60 → baseline + current window
    for v in baseline_vals:
        monitor.record_prediction(
            model_version="v1",
            symbol="XAUUSD",
            predicted_label=1,
            feature_snapshot={"f1": v},
        )
    for v in current_vals:
        monitor.record_prediction(
            model_version="v1",
            symbol="XAUUSD",
            predicted_label=1,
            feature_snapshot={"f1": v},
        )

    report = monitor.check_drift("v1", "XAUUSD")
    assert "f1" in report.feature_drift_scores

    # Independent recomputation: baseline = all 100 values, current = last 60.
    all_vals = baseline_vals + current_vals
    b_mean = sum(all_vals) / len(all_vals)
    b_std = max((sum((v - b_mean) ** 2 for v in all_vals) / len(all_vals)) ** 0.5, 1e-10)
    c_mean = sum(current_vals) / len(current_vals)
    c_std = max((sum((v - c_mean) ** 2 for v in current_vals) / len(current_vals)) ** 0.5, 1e-10)
    expected = psi(baseline_mean=b_mean, baseline_std=b_std, current_mean=c_mean, current_std=c_std)
    # DriftMonitor rounds scores to 6 decimals (ml/drift_monitor.py:460).
    assert report.feature_drift_scores["f1"] == pytest.approx(expected, abs=1e-6)
