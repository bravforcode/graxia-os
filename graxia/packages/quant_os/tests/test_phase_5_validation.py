"""Phase 5 — Validation module tests."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from validation.experiment_registry import ExperimentRecord, ExperimentRegistry
from validation.walk_forward import walk_forward_split


def _make_record(experiment_id="exp-001", strategy_hash="abc123"):
    return ExperimentRecord(
        experiment_id=experiment_id,
        git_commit="deadbeef",
        strategy_snapshot_hash=strategy_hash,
        parameter_snapshot_hash="param_hash",
        dataset_manifest_ids=["ds-1"],
        contract_snapshot_id="contract-1",
        execution_model_id="exec-1",
        cost_scenario_id="cost-1",
        risk_policy_id="risk-1",
    )


def test_experiment_registry_register():
    reg = ExperimentRegistry()
    rec = _make_record()
    eid = reg.register(rec)
    assert eid == "exp-001"
    assert reg.get("exp-001") is rec
    assert reg.count() == 1


def test_experiment_registry_duplicate_rejected():
    reg = ExperimentRegistry()
    reg.register(_make_record())
    try:
        reg.register(_make_record())
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_experiment_registry_budget_check():
    reg = ExperimentRegistry()
    strategy_hash = "abc123"
    for i in range(11):
        reg.register(_make_record(experiment_id=f"exp-{i:03d}", strategy_hash=strategy_hash))
    assert reg.check_budget(strategy_hash, budget=12) is True
    reg.register(_make_record(experiment_id="exp-011", strategy_hash=strategy_hash))
    assert reg.check_budget(strategy_hash, budget=12) is False


def test_walk_forward_split_count():
    splits = walk_forward_split(n_bars=1000, n_folds=5)
    assert len(splits) == 5


def test_walk_forward_split_no_leakage():
    splits = walk_forward_split(n_bars=1000, n_folds=5, embargo_bars=10)
    for (tr_s, tr_e), (te_s, te_e) in splits:
        assert tr_e <= te_s, f"Leakage: train ends at {tr_e}, test starts at {te_s}"


def test_experiment_fingerprint_deterministic():
    rec = _make_record()
    assert rec.fingerprint() == rec.fingerprint()
    rec2 = _make_record(experiment_id="exp-002")
    assert rec.fingerprint() != rec2.fingerprint()
