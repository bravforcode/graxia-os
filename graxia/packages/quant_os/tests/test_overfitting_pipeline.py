"""Integration test — full overfitting detection pipeline end-to-end."""

import random

import numpy as np

from graxia.packages.quant_os.validation import (
    OverfittingConfig,
    OverfittingDetector,
    OverfittingReport,
    SearchBudgetTracker,
    analyze_cost_sensitivity,
    analyze_parameter_stability,
    benjamini_hochberg,
    bootstrap_confidence_interval,
    calculate_pbo,
    deflated_sharpe_ratio,
    min_backtest_length,
)


def test_full_pipeline_clean_strategy():
    """Clean strategy passes through the full pipeline."""
    # 1. Simulate a good strategy with realistic returns
    rng = random.Random(42)
    returns = [rng.gauss(0.001, 0.008) for _ in range(5000)]

    # 2. DSR — few trials, high Sharpe
    sr_mean = sum(returns) / len(returns)
    sr_std = (sum((r - sr_mean) ** 2 for r in returns) / (len(returns) - 1)) ** 0.5
    observed_sharpe = (sr_mean / sr_std) * (252**0.5) if sr_std > 0 else 0

    dsr = deflated_sharpe_ratio(observed_sharpe=observed_sharpe, n_trials=20, n_observations=5000)
    assert dsr.observed_sharpe > 0

    # 3. MinBTL — should have enough data
    btl = min_backtest_length(observed_sharpe=observed_sharpe, n_trials=20, current_observations=5000)
    assert btl.min_observations > 0

    # 4. PBO — good OOS folds
    folds = [[rng.gauss(0.001, 0.008) for _ in range(500)] for _ in range(6)]
    pbo = calculate_pbo(folds)
    assert 0 <= pbo.pbo <= 1

    # 5. Bootstrap
    boot = bootstrap_confidence_interval(returns, n_resamples=500)
    assert boot.confidence_interval_95[0] != boot.confidence_interval_95[1]

    # 6. Cost stress
    cost = analyze_cost_sensitivity(base_pnl=10000, total_costs=2000)
    assert cost.cost_sensitivity in ("NONE", "LOW", "MEDIUM", "HIGH")

    # 7. Parameter stability
    stability = analyze_parameter_stability(
        parameter_name="lookback",
        base_value=20,
        nearby_values=[18, 19, 20, 21, 22],
        pnls=[950, 980, 1000, 970, 940],
    )
    assert stability.stability_score > 0

    # 8. Full detector
    detector = OverfittingDetector()
    report = detector.evaluate(
        strategy_id="clean_strategy",
        returns=returns,
        n_trials=20,
        n_observations=5000,
        oos_returns_per_fold=folds,
        cost_pnl=10000,
        total_costs=2000,
        param_values=[18, 19, 20, 21, 22],
        param_pnls=[950, 980, 1000, 970, 940],
        data_length=5000,
    )
    assert isinstance(report.score, float)
    assert report.recommendation in ("PROCEED", "RETURN_TO_RESEARCH", "ARCHIVE_NO_EDGE")


def test_search_budget_integration():
    """SearchBudgetTracker integrates with DSR correctly."""
    tracker = SearchBudgetTracker(max_trials=1000)

    # Record 200 trials
    for i in range(200):
        tracker.record_trial("strat_a", {"param": i}, is_sharpe=1.0 + i * 0.01)

    assert tracker.get_trial_count("strat_a") == 200
    assert tracker.is_within_budget("strat_a") is True

    # DSR should use 200 as n_trials
    dsr = tracker.get_deflated_sharpe("strat_a", observed_sharpe=3.0, n_observations=5000)
    assert dsr.observed_sharpe == 3.0
    # With 200 trials, adjustment should be significant
    assert dsr.multiple_testing_adjustment > 0


def test_bh_fdr_integration():
    """Benjamini-Hochberg FDR correction works."""
    pvals = [0.001, 0.01, 0.03, 0.05, 0.5]
    rejected, adjusted = benjamini_hochberg(pvals, alpha=0.05)
    assert len(rejected) == 5
    assert rejected[0] is np.bool_(True) or rejected[0] is True  # smallest p-value should be rejected


def test_full_pipeline_imports():
    """All validation modules import cleanly from package root."""
    from graxia.packages.quant_os.validation import (
        OverfittingDetector,
        SearchBudgetTracker,
        analyze_cost_sensitivity,
        analyze_parameter_stability,
        benjamini_hochberg,
        bootstrap_confidence_interval,
        calculate_pbo,
        deflated_sharpe_ratio,
        min_backtest_length,
    )

    # If we get here, all imports succeeded
    assert callable(deflated_sharpe_ratio)
    assert callable(min_backtest_length)
    assert callable(calculate_pbo)
    assert callable(bootstrap_confidence_interval)
    assert callable(benjamini_hochberg)
    assert callable(analyze_parameter_stability)
    assert callable(analyze_cost_sensitivity)
    assert OverfittingDetector is not None
    assert OverfittingConfig is not None
    assert SearchBudgetTracker is not None


def test_detector_with_tracker():
    """OverfittingDetector works with SearchBudgetTracker trial counts."""
    tracker = SearchBudgetTracker(max_trials=500)

    # Simulate 150 trials
    for i in range(150):
        tracker.record_trial("xau_v1", {"lookback": 10 + i}, is_sharpe=1.0 + i * 0.005)

    # Get the DSR from tracker
    dsr = tracker.get_deflated_sharpe("xau_v1", observed_sharpe=2.0, n_observations=5000)
    assert dsr.observed_sharpe == 2.0

    # Now run full detector with same trial count
    rng = random.Random(42)
    returns = [rng.gauss(0.001, 0.008) for _ in range(5000)]
    folds = [[rng.gauss(0.001, 0.008) for _ in range(500)] for _ in range(6)]

    detector = OverfittingDetector()
    report = detector.evaluate(
        strategy_id="xau_v1",
        returns=returns,
        n_trials=150,  # match tracker count
        n_observations=5000,
        oos_returns_per_fold=folds,
        cost_pnl=10000,
        total_costs=2000,
        param_values=[18, 19, 20, 21, 22],
        param_pnls=[950, 980, 1000, 970, 940],
        data_length=5000,
    )
    assert isinstance(report, OverfittingReport)
    # Detector auto-computes Sharpe from returns; both should be positive
    assert report.dsr_result.observed_sharpe > 0
    assert dsr.observed_sharpe > 0
    # Both used 150 trials → same multiple_testing_adjustment
    assert abs(report.dsr_result.multiple_testing_adjustment - dsr.multiple_testing_adjustment) < 0.01


def test_pipeline_overfitted_vs_clean():
    """Overfitted strategy scores lower than clean strategy."""
    rng = random.Random(42)

    # Clean strategy: few trials, good returns, good OOS
    clean_returns = [rng.gauss(0.002, 0.005) for _ in range(5000)]
    clean_folds = [[rng.gauss(0.002, 0.005) for _ in range(500)] for _ in range(6)]

    detector = OverfittingDetector()
    clean_report = detector.evaluate(
        strategy_id="clean",
        returns=clean_returns,
        n_trials=10,
        n_observations=5000,
        oos_returns_per_fold=clean_folds,
        cost_pnl=10000,
        total_costs=500,
        param_values=[18, 19, 20, 21, 22],
        param_pnls=[950, 980, 1000, 970, 940],
        data_length=5000,
    )

    # Overfitted strategy: many trials, costs exceed PnL
    bad_returns = [rng.gauss(0.001, 0.01) for _ in range(5000)]
    bad_folds = [[rng.gauss(-0.002, 0.01) for _ in range(500)] for _ in range(6)]

    overfitted_report = detector.evaluate(
        strategy_id="overfitted",
        returns=bad_returns,
        n_trials=1000,
        n_observations=5000,
        oos_returns_per_fold=bad_folds,
        cost_pnl=500,
        total_costs=2000,
        param_values=[10, 15, 20, 25, 30],
        param_pnls=[-100, 200, 1000, 100, -500],
        data_length=5000,
    )

    # Clean should score higher
    assert clean_report.score >= overfitted_report.score


def test_dsr_multiple_testing_adjustment():
    """DSR adjustment increases with more trials."""
    r1 = deflated_sharpe_ratio(observed_sharpe=2.0, n_trials=10, n_observations=5000)
    r10 = deflated_sharpe_ratio(observed_sharpe=2.0, n_trials=100, n_observations=5000)
    r100 = deflated_sharpe_ratio(observed_sharpe=2.0, n_trials=1000, n_observations=5000)
    assert r1.multiple_testing_adjustment < r10.multiple_testing_adjustment < r100.multiple_testing_adjustment


def test_min_btl_sufficient_insufficient():
    """MinBTL correctly identifies sufficient vs insufficient data."""
    # High Sharpe, few trials → should be sufficient with 5000 bars
    s = min_backtest_length(observed_sharpe=3.0, n_trials=10, current_observations=5000)
    assert s.sufficient is True

    # Low trials but need to check high trial count
    ns = min_backtest_length(observed_sharpe=3.0, n_trials=100000, current_observations=5000)
    # With 100k trials, 5000 bars likely insufficient
    assert ns.sufficient is False
