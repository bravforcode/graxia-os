# tests/test_n_trials_i.py
import json

from validation.n_trials_i import count_distinct_configs, get_n_i


def _log(configs):
    return {"schema_version": "1.0", "direction": "I", "configs": configs, "count": len(configs)}


CFG_A = {"config_id": "a1", "hash": "h1", "status": "done"}
CFG_A_DUP = {"config_id": "a2", "hash": "h1", "status": "done"}  # same hash = same config
CFG_B = {"config_id": "b1", "hash": "h2", "status": "done"}
CFG_VOID = {"config_id": "c1", "hash": "h3", "status": "VOID"}


def test_count_distinct_configs_dedups_by_hash():
    assert count_distinct_configs(_log([CFG_A, CFG_A_DUP, CFG_B, CFG_VOID])) == 3


def test_count_distinct_configs_empty():
    assert count_distinct_configs(_log([])) == 0


def test_get_n_i_empty_logs_uses_baseline():
    assert get_n_i(baseline=1050) == 1050


def test_get_n_i_adds_configs_and_trials(tmp_path):
    screening = tmp_path / "screening_log_i.json"
    screening.write_text(json.dumps(_log([CFG_A, CFG_B, CFG_VOID])), encoding="utf-8")
    ledger = tmp_path / "trial_ledger_i.json"
    ledger.write_text(json.dumps({"cumulative_trial_count": 2}), encoding="utf-8")
    n = get_n_i(
        screening_log_path=str(screening),
        trial_ledger_path=str(ledger),
        baseline=1050,
    )
    # 1050 + 3 distinct configs (VOID still counts) + 2 trials = 1055
    assert n == 1055
