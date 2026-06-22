import pytest
from governance.experiment_registry import ExperimentRecord, ExperimentRegistry
from governance.trial_budget import TrialBudget
from governance.validation_stack import (
    ValidationStack, DataLeakageTest, FeatureAvailabilityTest,
    WalkForwardValidation, DeflatedSharpeRatio, PBOCheck, ParameterStability
)
from governance.ml_policy import MLPolicyGuard, MLUsageType, MLPhase, MLModelRecord

def _make_record(experiment_id="EXP-001", strategy_hash="s1", parameter_hash="p1", trial=1, budget=12):
    return ExperimentRecord(
        experiment_id=experiment_id,
        git_commit="abc123",
        strategy_hash=strategy_hash,
        parameter_hash=parameter_hash,
        dataset_manifest_ids=["ds1"],
        contract_snapshot_id="cs1",
        execution_model_version="1.0",
        risk_policy_version="1.0",
        feature_set_hash="fs1",
        random_seed=42,
        trial_number=trial,
        trial_budget=budget,
    )

class TestExperimentRegistry:
    def test_register(self):
        reg = ExperimentRegistry()
        r = _make_record()
        ok, msg = reg.register(r)
        assert ok is True
    
    def test_duplicate_rejected(self):
        reg = ExperimentRegistry()
        reg.register(_make_record())
        ok, msg = reg.register(_make_record())
        assert ok is False
    
    def test_budget_exceeded(self):
        reg = ExperimentRegistry()
        r = _make_record(trial=15, budget=12)
        ok, msg = reg.register(r)
        assert ok is False
        assert "BUDGET_EXCEEDED" in msg
    
    def test_list_by_strategy(self):
        reg = ExperimentRegistry()
        reg.register(_make_record(experiment_id="E1", strategy_hash="s1"))
        reg.register(_make_record(experiment_id="E2", strategy_hash="s1"))
        reg.register(_make_record(experiment_id="E3", strategy_hash="s2"))
        assert len(reg.list_by_strategy("s1")) == 2
    
    def test_export_json(self):
        reg = ExperimentRegistry()
        reg.register(_make_record())
        j = reg.export_json()
        assert "EXP-001" in j

class TestTrialBudget:
    def test_increment_parameter(self):
        budget = TrialBudget()
        ok, msg = budget.increment_parameter()
        assert ok is True
        assert budget.parameter_trials_used == 1
    
    def test_parameter_exceeded(self):
        budget = TrialBudget(max_parameter_trials=2)
        budget.increment_parameter()
        budget.increment_parameter()
        ok, msg = budget.increment_parameter()
        assert ok is False
    
    def test_is_exceeded(self):
        budget = TrialBudget(max_parameter_trials=1)
        budget.increment_parameter()
        assert budget.is_exceeded() is False
        budget.parameter_trials_used = 2
        assert budget.is_exceeded() is True
    
    def test_remaining(self):
        budget = TrialBudget(max_parameter_trials=12)
        budget.increment_parameter()
        r = budget.remaining()
        assert r["parameter_trials"] == 11
    
    def test_summary(self):
        budget = TrialBudget()
        s = budget.summary()
        assert "remaining" in s
        assert "is_exceeded" in s

class TestDataLeakage:
    def test_no_leakage(self):
        test = DataLeakageTest()
        check = test.run(100, 200, [50, 80, 99])
        assert check.passed is True
    
    def test_leakage_detected(self):
        test = DataLeakageTest()
        check = test.run(100, 200, [50, 150])
        assert check.passed is False

class TestFeatureAvailability:
    def test_all_available(self):
        test = FeatureAvailabilityTest()
        check = test.run(["f1", "f2"], {"f1": True, "f2": True})
        assert check.passed is True
    
    def test_missing_feature(self):
        test = FeatureAvailabilityTest()
        check = test.run(["f1", "f2"], {"f1": True})
        assert check.passed is False

class TestWalkForward:
    def test_passing_folds(self):
        test = WalkForwardValidation()
        check = test.run([{"oos_sharpe": 0.5}, {"oos_sharpe": 0.3}])
        assert check.passed is True
    
    def test_no_folds(self):
        test = WalkForwardValidation()
        check = test.run([])
        assert check.passed is False

class TestDeflatedSharpe:
    def test_passing_dsr(self):
        test = DeflatedSharpeRatio()
        check = test.run(sharpe=2.5, n_trials=10, n_bars=1000)
        assert check.passed is True

class TestPBO:
    def test_low_degradation(self):
        test = PBOCheck()
        check = test.run(is_sharpe=1.0, oos_sharpe=0.8)
        assert check.passed is True
    
    def test_high_degradation(self):
        test = PBOCheck()
        check = test.run(is_sharpe=1.0, oos_sharpe=0.2)
        assert check.passed is False

class TestParameterStability:
    def test_stable(self):
        test = ParameterStability()
        check = test.run(
            [{"p1": 1}, {"p1": 2}, {"p1": 3}],
            [0.5, 0.3, 0.4],
        )
        assert check.passed is True
    
    def test_insufficient(self):
        test = ParameterStability()
        check = test.run([{"p1": 1}], [0.5])
        assert check.passed is False

class TestMLPolicy:
    def test_allowed_usage(self):
        guard = MLPolicyGuard()
        ok, reason = guard.check_usage(MLUsageType.REGIME_CLASSIFICATION)
        assert ok is True
    
    def test_forbidden_usage(self):
        guard = MLPolicyGuard()
        ok, reason = guard.check_usage(MLUsageType.PRICE_PREDICTION)
        assert ok is False
    
    def test_online_training_forbidden(self):
        guard = MLPolicyGuard()
        ok, reason = guard.check_online_training(MLPhase.DEMO)
        assert ok is False
    
    def test_self_promotion_forbidden(self):
        guard = MLPolicyGuard()
        ok, reason = guard.check_self_promotion("model_a", "model_a")
        assert ok is False

class TestValidationStack:
    def test_run_all(self):
        stack = ValidationStack()
        result = stack.run_all(
            train_end_index=100, total_bars=200, feature_timestamps=[50, 80],
            feature_names=["f1"], available_features={"f1": True},
            folds=[{"oos_sharpe": 0.5}],
            sharpe=1.0, n_trials=5, n_bars=500,
            is_sharpe=1.0, oos_sharpe=0.8,
            param_sets=[{"p": 1}, {"p": 2}, {"p": 3}],
            performance=[0.5, 0.3, 0.4],
        )
        assert len(result.checks) >= 5
