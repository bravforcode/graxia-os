"""Tests for MinBTL — Minimum Backtest Length calculation."""

from graxia.packages.quant_os.validation.deflated_sharpe import min_backtest_length


def test_min_btl_basic():
    """Basic test: high Sharpe with few trials needs fewer observations."""
    result = min_backtest_length(observed_sharpe=3.0, n_trials=10)
    assert result.min_observations > 0
    assert result.n_trials == 10
    assert result.observed_sharpe == 3.0


def test_min_btl_increases_with_trials():
    """More trials → more observations needed."""
    r1 = min_backtest_length(observed_sharpe=2.0, n_trials=10)
    r2 = min_backtest_length(observed_sharpe=2.0, n_trials=1000)
    assert r2.min_observations > r1.min_observations


def test_min_btl_sufficient_data():
    """current_observations >= min_observations → sufficient=True."""
    result = min_backtest_length(observed_sharpe=3.0, n_trials=10, current_observations=100000)
    assert result.sufficient is True


def test_min_btl_insufficient_data():
    """current_observations < min_observations → sufficient=False."""
    result = min_backtest_length(observed_sharpe=3.0, n_trials=10000, current_observations=10)
    assert result.sufficient is False


def test_min_btl_low_sharpe():
    """Very low Sharpe returns very large min_observations (sentinel)."""
    result = min_backtest_length(observed_sharpe=0.01, n_trials=100)
    # Low Sharpe may fall below expected_max_sharpe → sentinel 999_999_999
    assert result.min_observations > 10000


def test_min_btl_zero_trials():
    """Edge case: zero trials returns min_observations=1."""
    result = min_backtest_length(observed_sharpe=2.0, n_trials=0)
    assert result.min_observations == 1
    assert result.n_trials == 0


def test_min_btl_negative_trials():
    """Edge case: negative trials treated same as zero."""
    result = min_backtest_length(observed_sharpe=2.0, n_trials=-5)
    assert result.min_observations == 1


def test_min_btl_result_fields():
    """MinBTLResult has all expected fields."""
    result = min_backtest_length(observed_sharpe=2.0, n_trials=50)
    assert hasattr(result, "min_observations")
    assert hasattr(result, "n_trials")
    assert hasattr(result, "observed_sharpe")
    assert hasattr(result, "expected_max_sharpe")
    assert hasattr(result, "z_threshold")
    assert hasattr(result, "sufficient")


def test_min_btl_no_current_observations():
    """When current_observations is None, sufficient is False."""
    result = min_backtest_length(observed_sharpe=2.0, n_trials=50)
    assert result.sufficient is False


def test_min_btl_high_sharpe_low_trials():
    """High Sharpe with very few trials: should need relatively few observations."""
    result = min_backtest_length(observed_sharpe=5.0, n_trials=5)
    # Very high Sharpe should overcome small trial count
    assert result.min_observations < 10000
    assert result.min_observations > 0


def test_min_btl_expected_max_sharpe_positive():
    """expected_max_sharpe should be positive for n_trials > 1."""
    result = min_backtest_length(observed_sharpe=3.0, n_trials=100)
    assert result.expected_max_sharpe > 0


def test_min_btl_z_threshold_at_95():
    """z_threshold at 95% confidence should be ~1.645."""
    result = min_backtest_length(observed_sharpe=3.0, n_trials=10, confidence_level=0.95)
    assert abs(result.z_threshold - 1.645) < 0.05


def test_min_btl_custom_confidence():
    """Different confidence levels produce different z_thresholds."""
    r95 = min_backtest_length(observed_sharpe=3.0, n_trials=10, confidence_level=0.95)
    r99 = min_backtest_length(observed_sharpe=3.0, n_trials=10, confidence_level=0.99)
    assert r99.z_threshold > r95.z_threshold
    # Higher confidence → more observations needed
    assert r99.min_observations >= r95.min_observations


def test_min_btl_zero_sharpe():
    """Zero Sharpe returns sentinel (very large min_observations)."""
    result = min_backtest_length(observed_sharpe=0.0, n_trials=10)
    assert result.min_observations == 999_999_999
    assert result.sufficient is False


def test_min_btl_negative_sharpe():
    """Negative Sharpe returns sentinel."""
    result = min_backtest_length(observed_sharpe=-1.0, n_trials=10)
    assert result.min_observations == 999_999_999
    assert result.sufficient is False
