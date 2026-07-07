"""Phase 5 integration tests — statistical validation."""

import pytest

from graxia.packages.quant_os.validation.bootstrap_sensitivity import bootstrap_confidence_interval
from graxia.packages.quant_os.validation.cost_stress import analyze_cost_sensitivity
from graxia.packages.quant_os.validation.deflated_sharpe import deflated_sharpe_ratio
from graxia.packages.quant_os.validation.experiment_registry import ExperimentRecord, ExperimentRegistry
from graxia.packages.quant_os.validation.parameter_stability import analyze_parameter_stability
from graxia.packages.quant_os.validation.probability_overfitting import calculate_pbo
from graxia.packages.quant_os.validation.walk_forward import walk_forward_split


def test_experiment_registry_works():
    reg = ExperimentRegistry()
    record = ExperimentRecord(
        experiment_id="TEST-001",
        git_commit="abc123",
        strategy_snapshot_hash="def456",
        parameter_snapshot_hash="ghi789",
        dataset_manifest_ids=["d1"],
        contract_snapshot_id="c1",
        execution_model_id="e1",
        cost_scenario_id="base",
        risk_policy_id="r1",
    )
    reg.clear()
    reg.register(record)
    assert reg.count() == 1
    assert reg.check_budget("def456", budget=12)


def test_walk_forward_split_works():
    splits = walk_forward_split(n_bars=1000, n_folds=5)
    assert len(splits) > 0
    for (tr_start, tr_end), (te_start, te_end) in splits:
        assert te_start >= tr_end
        assert te_end > te_start


def test_deflated_sharpe_works():
    result = deflated_sharpe_ratio(
        observed_sharpe=1.5,
        n_trials=100,
        n_observations=252,
    )
    assert result.observed_sharpe == 1.5
    assert result.multiple_testing_adjustment > 0


def test_pbo_works():
    result = calculate_pbo(
        oos_returns_per_fold=[[0.01, 0.02], [0.03, -0.01], [0.02, 0.01]],
        n_partitions=4,
    )
    assert 0 <= result.pbo <= 1


def test_cost_stress_works():
    result = analyze_cost_sensitivity(base_pnl=1000, total_costs=200)
    assert result.base_pnl == 1000
    assert result.survives_stress_1
    assert result.cost_sensitivity in ("LOW", "MEDIUM", "HIGH")


def test_parameter_stability_works():
    result = analyze_parameter_stability(
        parameter_name="lookback",
        base_value=20,
        nearby_values=[15, 20, 25],
        pnls=[800, 1000, 900],
    )
    assert result.stable
    assert result.stability_score > 0


def test_bootstrap_works():
    result = bootstrap_confidence_interval(
        values=[0.01, 0.02, 0.03, 0.04, 0.05],
        n_resamples=100,
    )
    assert result.observed_value == pytest.approx(0.03, abs=1e-9)
    assert result.confidence_interval_95[0] < result.confidence_interval_95[1]
