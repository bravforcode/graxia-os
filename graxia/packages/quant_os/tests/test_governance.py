"""Tests for governance modules — experiment registry and ML policy."""

import pytest
from graxia.packages.quant_os.governance.experiment_registry import (
    ExperimentRecord, ExperimentRegistry,
)
from graxia.packages.quant_os.governance.ml_policy import (
    MLUsageType, MLPhase, MLPolicyGuard, MLModelRecord,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_experiment(exp_id="EXP-001", strategy_hash="abc123", trial=1, budget=10):
    return ExperimentRecord(
        experiment_id=exp_id,
        git_commit="deadbeef",
        strategy_hash=strategy_hash,
        parameter_hash="param_hash",
        dataset_manifest_ids=["ds1"],
        contract_snapshot_id="snap1",
        execution_model_version="v1",
        risk_policy_version="v1",
        feature_set_hash="feat1",
        random_seed=42,
        trial_number=trial,
        trial_budget=budget,
    )


def _make_model(model_id="m1", usage=MLUsageType.REGIME_CLASSIFICATION):
    return MLModelRecord(
        model_id=model_id,
        usage_type=usage,
        training_data_hash="td1",
        feature_schema_hash="fs1",
        model_version="v1",
        trained_at_utc="2025-01-01T00:00:00",
        training_period_start="2024-01-01",
        training_period_end="2024-12-31",
    )


# ---------------------------------------------------------------------------
# ExperimentRegistry
# ---------------------------------------------------------------------------

class TestExperimentRegistry:
    def test_register_succeeds(self):
        reg = ExperimentRegistry()
        rec = _make_experiment()
        ok, msg = reg.register(rec)
        assert ok is True
        assert msg == "REGISTERED"

    def test_duplicate_id_rejected(self):
        reg = ExperimentRegistry()
        rec1 = _make_experiment(exp_id="E1")
        rec2 = _make_experiment(exp_id="E1")
        reg.register(rec1)
        ok, msg = reg.register(rec2)
        assert ok is False
        assert "DUPLICATE" in msg

    def test_budget_exceeded_rejected(self):
        reg = ExperimentRegistry()
        rec = _make_experiment(trial=20, budget=10)
        ok, msg = reg.register(rec)
        assert ok is False
        assert "BUDGET_EXCEEDED" in msg

    def test_get_returns_record(self):
        reg = ExperimentRegistry()
        rec = _make_experiment(exp_id="E2")
        reg.register(rec)
        assert reg.get("E2") is rec

    def test_get_unknown_returns_none(self):
        reg = ExperimentRegistry()
        assert reg.get("UNKNOWN") is None

    def test_is_registered(self):
        reg = ExperimentRegistry()
        rec = _make_experiment(exp_id="E3")
        assert reg.is_registered("E3") is False
        reg.register(rec)
        assert reg.is_registered("E3") is True

    def test_list_by_strategy(self):
        reg = ExperimentRegistry()
        reg.register(_make_experiment(exp_id="E1", strategy_hash="S1"))
        reg.register(_make_experiment(exp_id="E2", strategy_hash="S1"))
        reg.register(_make_experiment(exp_id="E3", strategy_hash="S2"))
        assert len(reg.list_by_strategy("S1")) == 2
        assert len(reg.list_by_strategy("S2")) == 1

    def test_count_trials(self):
        reg = ExperimentRegistry()
        reg.register(_make_experiment(exp_id="E1", strategy_hash="S1"))
        reg.register(_make_experiment(exp_id="E2", strategy_hash="S1"))
        assert reg.count_trials("S1") == 2
        assert reg.count_trials("S99") == 0

    def test_list_all(self):
        reg = ExperimentRegistry()
        reg.register(_make_experiment(exp_id="E1"))
        reg.register(_make_experiment(exp_id="E2"))
        assert len(reg.list_all()) == 2

    def test_export_json_is_valid(self):
        import json
        reg = ExperimentRegistry()
        reg.register(_make_experiment(exp_id="E1"))
        exported = reg.export_json()
        data = json.loads(exported)
        assert isinstance(data, list)
        assert data[0]["experiment_id"] == "E1"

    def test_fingerprint_is_deterministic(self):
        rec = _make_experiment()
        fp1 = rec.fingerprint()
        fp2 = rec.fingerprint()
        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# MLPolicyGuard
# ---------------------------------------------------------------------------

class TestMLPolicyGuard:
    def test_allowed_usage(self):
        guard = MLPolicyGuard()
        ok, msg = guard.check_usage(MLUsageType.REGIME_CLASSIFICATION)
        assert ok is True
        assert "ALLOWED" in msg

    def test_forbidden_usage_price_prediction(self):
        guard = MLPolicyGuard()
        ok, msg = guard.check_usage(MLUsageType.PRICE_PREDICTION)
        assert ok is False
        assert "FORBIDDEN" in msg

    def test_forbidden_usage_hyperparameter_selection(self):
        guard = MLPolicyGuard()
        ok, msg = guard.check_usage(MLUsageType.HYPERPARAMETER_SELECTION)
        assert ok is False
        assert "FORBIDDEN" in msg

    def test_register_model_allowed(self):
        guard = MLPolicyGuard()
        rec = _make_model()
        ok, msg = guard.register_model(rec)
        assert ok is True

    def test_register_model_forbidden(self):
        guard = MLPolicyGuard()
        rec = _make_model(usage=MLUsageType.PRICE_PREDICTION)
        ok, msg = guard.register_model(rec)
        assert ok is False
        assert "FORBIDDEN" in msg

    def test_check_controls_missing_schema(self):
        guard = MLPolicyGuard()
        rec = MLModelRecord(
            model_id="m1",
            usage_type=MLUsageType.ANOMALY_DETECTION,
            training_data_hash="td1",
            feature_schema_hash="",  # missing
            model_version="v1",
            trained_at_utc="2025-01-01",
            training_period_start="2024-01-01",
            training_period_end="2024-12-31",
        )
        guard.register_model(rec)
        ok, issues = guard.check_controls("m1", MLPhase.SHADOW)
        assert ok is False
        assert "MISSING_FEATURE_SCHEMA" in issues

    def test_check_controls_live_forbidden(self):
        guard = MLPolicyGuard()
        rec = _make_model()
        guard.register_model(rec)
        ok, issues = guard.check_controls("m1", MLPhase.LIVE)
        assert ok is False
        assert "LIVE_ML_NOT_ALLOWED" in issues

    def test_check_controls_training_ok(self):
        guard = MLPolicyGuard()
        rec = _make_model()
        guard.register_model(rec)
        ok, issues = guard.check_controls("m1", MLPhase.TRAINING)
        assert ok is True
        assert issues == []

    def test_check_online_training_forbidden_in_live(self):
        guard = MLPolicyGuard()
        ok, msg = guard.check_online_training(MLPhase.LIVE)
        assert ok is False
        assert "FORBIDDEN" in msg

    def test_check_online_training_allowed_in_training(self):
        guard = MLPolicyGuard()
        ok, msg = guard.check_online_training(MLPhase.TRAINING)
        assert ok is True

    def test_check_self_promotion_forbidden(self):
        guard = MLPolicyGuard()
        ok, msg = guard.check_self_promotion("model_A", "model_A")
        assert ok is False
        assert "SELF_PROMOTION" in msg

    def test_check_self_promotion_allowed(self):
        guard = MLPolicyGuard()
        ok, msg = guard.check_self_promotion("model_A", "admin")
        assert ok is True

    def test_check_scaler_fit_match(self):
        guard = MLPolicyGuard()
        ok, msg = guard.check_scaler_fit("2024-Q1", "2024-Q1")
        assert ok is True

    def test_check_scaler_fit_mismatch(self):
        guard = MLPolicyGuard()
        ok, msg = guard.check_scaler_fit("2024-Q1", "2024-Q2")
        assert ok is False
        assert "MISMATCH" in msg

    def test_list_models(self):
        guard = MLPolicyGuard()
        guard.register_model(_make_model(model_id="m1"))
        guard.register_model(_make_model(model_id="m2"))
        assert len(guard.list_models()) == 2
