"""Tests for OverfittingDetector — unified overfitting detection pipeline."""

import random

from graxia.packages.quant_os.validation.overfitting_detector import (
    OverfittingConfig,
    OverfittingDetector,
    OverfittingReport,
)


def _make_returns(n=5000, mean=0.001, std=0.01, seed=42):
    """Generate synthetic returns."""
    rng = random.Random(seed)
    return [rng.gauss(mean, std) for _ in range(n)]


def _make_oos_folds(n_folds=5, n_returns=500, mean=0.001, std=0.01, seed=42):
    """Generate synthetic OOS returns per fold."""
    rng = random.Random(seed)
    return [[rng.gauss(mean, std) for _ in range(n_returns)] for _ in range(n_folds)]


def test_detector_basic():
    """OverfittingDetector evaluates without error."""
    detector = OverfittingDetector()
    returns = _make_returns()
    folds = _make_oos_folds()
    report = detector.evaluate(
        strategy_id="test",
        returns=returns,
        n_trials=50,
        n_observations=5000,
        oos_returns_per_fold=folds,
        cost_pnl=10000,
        total_costs=2000,
        param_values=[18, 19, 20, 21, 22],
        param_pnls=[950, 980, 1000, 970, 940],
        data_length=5000,
    )
    assert isinstance(report, OverfittingReport)
    assert report.strategy_id == "test"
    assert 0 <= report.score <= 1
    assert report.recommendation in ("PROCEED", "RETURN_TO_RESEARCH", "ARCHIVE_NO_EDGE")


def test_report_has_all_components():
    """Report includes results from all checks."""
    detector = OverfittingDetector()
    report = detector.evaluate(
        strategy_id="test",
        returns=_make_returns(),
        n_trials=50,
        n_observations=5000,
        oos_returns_per_fold=_make_oos_folds(),
        cost_pnl=10000,
        total_costs=2000,
        param_values=[18, 19, 20, 21, 22],
        param_pnls=[950, 980, 1000, 970, 940],
        data_length=5000,
    )
    assert report.dsr_result is not None
    assert report.pbo_result is not None
    assert report.bootstrap_result is not None
    assert report.cost_stress_result is not None
    assert report.min_btl_result is not None


def test_overfitted_strategy_detected():
    """Strategy with bad OOS is detected as overfitted."""
    detector = OverfittingDetector()
    # Good IS returns but bad OOS folds
    returns = _make_returns(mean=0.005, std=0.005)  # good returns
    bad_folds = _make_oos_folds(mean=-0.005, std=0.01)  # bad OOS
    report = detector.evaluate(
        strategy_id="overfitted",
        returns=returns,
        n_trials=500,
        n_observations=5000,
        oos_returns_per_fold=bad_folds,
        cost_pnl=100,
        total_costs=200,  # costs kill profit
        param_values=[10, 15, 20, 25, 30],
        param_pnls=[100, 500, 1000, 200, -100],
        data_length=5000,
    )
    # Should have blockers or low score
    assert report.score < 0.7 or len(report.blockers) > 0


def test_custom_config():
    """OverfittingConfig customizes thresholds."""
    config = OverfittingConfig(max_pbo=0.1, min_deflated_sharpe=0.9)
    detector = OverfittingDetector(config=config)
    report = detector.evaluate(
        strategy_id="strict",
        returns=_make_returns(),
        n_trials=10,
        n_observations=5000,
        oos_returns_per_fold=_make_oos_folds(),
        cost_pnl=10000,
        total_costs=100,
        param_values=[20],
        param_pnls=[1000],
        data_length=5000,
    )
    assert isinstance(report, OverfittingReport)


def test_empty_folds():
    """Empty OOS folds handled gracefully — PBO defaults to 1.0."""
    detector = OverfittingDetector()
    report = detector.evaluate(
        strategy_id="no_folds",
        returns=_make_returns(),
        n_trials=10,
        n_observations=5000,
        oos_returns_per_fold=[],
        cost_pnl=10000,
        total_costs=100,
        param_values=[20],
        param_pnls=[1000],
        data_length=5000,
    )
    assert report.pbo_result is not None
    assert report.pbo_result.pbo == 1.0  # no data = worst case


def test_composite_score_range():
    """Composite score is always between 0 and 1."""
    detector = OverfittingDetector()
    for seed in range(5):
        returns = _make_returns(seed=seed)
        folds = _make_oos_folds(seed=seed)
        report = detector.evaluate(
            strategy_id=f"test_{seed}",
            returns=returns,
            n_trials=50,
            n_observations=5000,
            oos_returns_per_fold=folds,
            cost_pnl=10000,
            total_costs=2000,
            param_values=[18, 19, 20, 21, 22],
            param_pnls=[950, 980, 1000, 970, 940],
            data_length=5000,
        )
        assert 0 <= report.score <= 1, f"Score {report.score} out of range for seed={seed}"


def test_report_timestamp():
    """Report has a valid ISO timestamp."""
    detector = OverfittingDetector()
    report = detector.evaluate(
        strategy_id="ts",
        returns=_make_returns(),
        n_trials=10,
        n_observations=5000,
        oos_returns_per_fold=_make_oos_folds(),
        cost_pnl=10000,
        total_costs=100,
        param_values=[20],
        param_pnls=[1000],
        data_length=5000,
    )
    assert report.timestamp  # not empty
    assert "T" in report.timestamp  # ISO format


def test_sharpe_auto_computed():
    """If sharpe=None, it's computed from returns."""
    detector = OverfittingDetector()
    returns = _make_returns(mean=0.002, std=0.005)
    report = detector.evaluate(
        strategy_id="auto_sharpe",
        returns=returns,
        n_trials=10,
        n_observations=5000,
        oos_returns_per_fold=_make_oos_folds(),
        cost_pnl=10000,
        total_costs=100,
        param_values=[20],
        param_pnls=[1000],
        data_length=5000,
    )
    assert report.dsr_result.observed_sharpe > 0


def test_sharpe_provided():
    """If sharpe is provided, it's used directly."""
    detector = OverfittingDetector()
    report = detector.evaluate(
        strategy_id="manual_sharpe",
        returns=_make_returns(),
        n_trials=10,
        n_observations=5000,
        oos_returns_per_fold=_make_oos_folds(),
        cost_pnl=10000,
        total_costs=100,
        param_values=[20],
        param_pnls=[1000],
        data_length=5000,
        sharpe=2.5,
    )
    assert report.dsr_result.observed_sharpe == 2.5


def test_report_passed_field():
    """passed is True only when recommendation is PROCEED."""
    detector = OverfittingDetector()
    report = detector.evaluate(
        strategy_id="pass_test",
        returns=_make_returns(),
        n_trials=10,
        n_observations=5000,
        oos_returns_per_fold=_make_oos_folds(),
        cost_pnl=10000,
        total_costs=100,
        param_values=[20],
        param_pnls=[1000],
        data_length=5000,
    )
    if report.recommendation == "PROCEED":
        assert report.passed is True
    else:
        assert report.passed is False


def test_empty_returns():
    """Empty returns handled gracefully."""
    detector = OverfittingDetector()
    report = detector.evaluate(
        strategy_id="empty",
        returns=[],
        n_trials=10,
        n_observations=0,
        oos_returns_per_fold=[],
        cost_pnl=0,
        total_costs=0,
        param_values=[],
        param_pnls=[],
        data_length=0,
    )
    assert isinstance(report, OverfittingReport)
    assert report.strategy_id == "empty"


def test_param_stability_results():
    """param_stability_results populated when params provided."""
    detector = OverfittingDetector()
    report = detector.evaluate(
        strategy_id="params",
        returns=_make_returns(),
        n_trials=10,
        n_observations=5000,
        oos_returns_per_fold=_make_oos_folds(),
        cost_pnl=10000,
        total_costs=100,
        param_values=[18, 19, 20, 21, 22],
        param_pnls=[950, 980, 1000, 970, 940],
        data_length=5000,
    )
    assert len(report.param_stability_results) > 0


def test_param_stability_empty():
    """Empty param lists produce empty stability results."""
    detector = OverfittingDetector()
    report = detector.evaluate(
        strategy_id="no_params",
        returns=_make_returns(),
        n_trials=10,
        n_observations=5000,
        oos_returns_per_fold=_make_oos_folds(),
        cost_pnl=10000,
        total_costs=100,
        param_values=[],
        param_pnls=[],
        data_length=5000,
    )
    assert len(report.param_stability_results) == 0


def test_high_cost_sensitivity():
    """Strategy with costs > PnL gets HIGH sensitivity blocker."""
    detector = OverfittingDetector()
    report = detector.evaluate(
        strategy_id="costly",
        returns=_make_returns(),
        n_trials=10,
        n_observations=5000,
        oos_returns_per_fold=_make_oos_folds(),
        cost_pnl=1000,
        total_costs=5000,  # costs far exceed PnL
        param_values=[20],
        param_pnls=[1000],
        data_length=5000,
    )
    assert report.cost_stress_result.cost_sensitivity == "HIGH"
    # Should be a blocker
    cost_blockers = [b for b in report.blockers if "cost" in b.lower() or "Cost" in b]
    assert len(cost_blockers) > 0


def test_config_max_trials():
    """OverfittingConfig has max_trials field."""
    config = OverfittingConfig(max_trials=500)
    assert config.max_trials == 500


def test_single_fold_pbo():
    """Single fold (insufficient for PBO) returns PBO=1.0."""
    detector = OverfittingDetector()
    folds = _make_oos_folds(n_folds=1)
    report = detector.evaluate(
        strategy_id="single_fold",
        returns=_make_returns(),
        n_trials=10,
        n_observations=5000,
        oos_returns_per_fold=folds,
        cost_pnl=10000,
        total_costs=100,
        param_values=[20],
        param_pnls=[1000],
        data_length=5000,
    )
    assert report.pbo_result.pbo == 1.0
