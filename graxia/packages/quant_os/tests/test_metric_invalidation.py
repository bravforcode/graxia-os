"""Test legacy metric invalidation enforcement."""
from graxia.packages.quant_os.risk.metric_invalidation import (
    get_metric_validity, is_metric_usable, MetricValidity
)

def test_gross_pnl_invalid():
    assert get_metric_validity("gross_pnl") == MetricValidity.INVALID_FOR_DECISION

def test_expectancy_invalid():
    assert get_metric_validity("expectancy") == MetricValidity.INVALID_FOR_DECISION

def test_win_rate_simulated_only():
    assert get_metric_validity("win_rate") == MetricValidity.SIMULATED_ONLY

def test_signal_count_partially_valid():
    assert get_metric_validity("signal_count") == MetricValidity.PARTIALLY_VALID

def test_process_restarts_valid():
    assert get_metric_validity("process_restarts") == MetricValidity.VALID

def test_pnl_not_usable():
    assert is_metric_usable("gross_pnl") == False

def test_uptime_usable():
    assert is_metric_usable("uptime_seconds") == True

def test_unknown_metric_returns_undetermined():
    assert get_metric_validity("nonexistent") == MetricValidity.UNDETERMINED

def test_shape_ratio_invalid_for_decision():
    assert get_metric_validity("sharpe_ratio") == MetricValidity.INVALID_FOR_DECISION

def test_all_registry_metrics_have_classification():
    from graxia.packages.quant_os.risk.metric_invalidation import LEGACY_METRIC_REGISTRY
    assert len(LEGACY_METRIC_REGISTRY) >= 17
    for key, val in LEGACY_METRIC_REGISTRY.items():
        assert isinstance(val, MetricValidity)
