"""Phase 5 — Statistical validation tests."""
import math
from graxia.packages.quant_os.validation.deflated_sharpe import deflated_sharpe_ratio
from graxia.packages.quant_os.validation.probability_overfitting import calculate_pbo


def test_deflated_sharpe_zero_trials():
    """Zero trials returns full penalty."""
    result = deflated_sharpe_ratio(observed_sharpe=1.0, n_trials=0, n_observations=100)
    assert result.observed_sharpe == 1.0
    assert result.deflated_sharpe == 1.0
    assert result.probability_alpha == 1.0
    assert result.passes_threshold is False


def test_deflated_sharpe_high_sharpe():
    """High Sharpe with many observations passes threshold."""
    result = deflated_sharpe_ratio(
        observed_sharpe=3.0, n_trials=10, n_observations=1000
    )
    assert result.observed_sharpe == 3.0
    assert result.deflated_sharpe > 0


def test_deflated_sharpe_multiple_testing_penalty():
    """More trials increases the adjustment, penalizing false positives."""
    low_trials = deflated_sharpe_ratio(observed_sharpe=1.5, n_trials=5, n_observations=500)
    high_trials = deflated_sharpe_ratio(observed_sharpe=1.5, n_trials=500, n_observations=500)
    assert high_trials.multiple_testing_adjustment > low_trials.multiple_testing_adjustment


def test_pbo_low_overfitting():
    """All-positive OOS returns → low PBO."""
    folds = [[0.01, 0.02, 0.03] for _ in range(10)]
    result = calculate_pbo(folds)
    assert 0 <= result.pbo <= 1
    assert result.pbo < 0.5  # most folds above mean (all equal)


def test_pbo_high_overfitting():
    """Mixed returns with many below mean → high PBO."""
    folds = [[0.1]] * 5 + [[-0.1]] * 5
    result = calculate_pbo(folds)
    assert result.pbo > 0.3


def test_pbo_insufficient_folds():
    """Single fold → PBO = 1.0."""
    result = calculate_pbo([[0.01, 0.02]])
    assert result.pbo == 1.0
    assert result.passes_threshold is False
