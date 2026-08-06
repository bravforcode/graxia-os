# tests/test_direction_i_ledgers.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ledger_i_exists_and_matches_governance():
    ledger = json.loads((ROOT / "research" / "trial_ledger_i.json").read_text(encoding="utf-8"))
    assert ledger["direction"] == "I"
    assert ledger["trial_range"] == "10000-10999"
    assert ledger["cumulative_trial_cap"] == 40
    assert ledger["next_available_trial_number"] == 10001
    assert ledger["stopping_rule"]["deadline"] is None  # user override: no time limit
    assert ledger["stopping_rule"]["hours_cap"] == 400
    assert ledger["stopping_rule"]["consecutive_fail_gate_threshold"] == 3
    assert ledger["sacred_holdout"]["status"] == "LOCKED"
    assert len(ledger["lock_doc_sha256"]) == 64


def test_registry_i_exists():
    reg = json.loads((ROOT / "research" / "hypothesis_registry_i.json").read_text(encoding="utf-8"))
    assert reg["direction"] == "I"
    assert reg["cumulative_trial_count_at_creation"] == 0


def test_screening_log_i_schema():
    log = json.loads((ROOT / "research" / "screening_log_i.json").read_text(encoding="utf-8"))
    assert log["schema_version"] == "1.0"
    assert log["direction"] == "I"
    assert log["configs"] == []
    assert log["count"] == 0


def test_ranges_table_has_direction_i():
    text = (ROOT / "TRIAL_ID_RANGES.md").read_text(encoding="utf-8")
    assert "| Direction I" in text
    assert "10000–10999" in text or "10000-10999" in text


def test_ranges_table_notes_creation_order():
    text = (ROOT / "TRIAL_ID_RANGES.md").read_text(encoding="utf-8")
    assert "creation order" in text.lower()
