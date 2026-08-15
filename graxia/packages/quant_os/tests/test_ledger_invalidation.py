"""Tests for research/ledger_invalidation.py (Phase 1 demote cross-reference)."""

from __future__ import annotations

import json

from graxia.packages.quant_os.research.ledger_invalidation import (
    _entry_references_symbol,
    invalidate_hypothesis_registry,
    invalidate_ledger,
    invalidate_symbol,
)


def test_entry_references_symbol_via_instrument():
    assert _entry_references_symbol({"instrument": "XAUUSD"}, "XAUUSD") is True
    assert _entry_references_symbol({"instrument": "XAUUSD/XAGUSD"}, "XAUUSD") is True
    assert _entry_references_symbol({"instrument": "BTCUSD"}, "XAUUSD") is False


def test_entry_references_symbol_via_universe_list():
    entry = {"universe": ["XAUUSD", "XAGUSD", "EURUSD"]}
    assert _entry_references_symbol(entry, "EURUSD") is True
    assert _entry_references_symbol(entry, "NAS100") is False


def test_entry_references_symbol_via_data_sources():
    entry = {"data_sources": ["data/USOIL_D1.csv"]}
    assert _entry_references_symbol(entry, "USOIL") is True


def test_invalidate_ledger_marks_and_is_idempotent():
    ledger = {"lineage": [{"id": "a", "note": "ran XAUUSD"}, {"id": "b", "note": "EURUSD only"}]}
    count = invalidate_ledger(ledger, "XAUUSD", "cost drift", "audit-1")
    assert count == 1
    assert ledger["lineage"][0]["provenance_invalidated"] is True
    assert ledger["lineage"][0]["provenance_invalidation"]["reason"] == "cost drift"
    assert ledger["lineage"][1].get("provenance_invalidated") is None

    # Idempotent: second pass marks nothing new and preserves the original keys.
    original_keys = set(ledger["lineage"][0].keys())
    count2 = invalidate_ledger(ledger, "XAUUSD", "cost drift", "audit-1")
    assert count2 == 0
    assert set(ledger["lineage"][0].keys()) == original_keys


def test_invalidate_hypothesis_registry_marks_matching():
    registry = {
        "hypotheses": [
            {"trial_number": 1001, "instrument": "XAUUSD"},
            {"trial_number": 1003, "instrument": "MULTI-ASSET", "universe": ["XAUUSD", "EURUSD"]},
            {"trial_number": 1004, "instrument": "BTCUSD"},
        ]
    }
    count = invalidate_hypothesis_registry(registry, "XAUUSD", "cost drift", "audit-2")
    assert count == 2
    assert registry["hypotheses"][0]["provenance_invalidated"] is True
    assert registry["hypotheses"][1]["provenance_invalidated"] is True
    assert registry["hypotheses"][2].get("provenance_invalidated") is None


def test_invalidate_symbol_writes_only_changed_files(tmp_path):
    ledger = tmp_path / "trial_ledger.json"
    ledger.write_text(json.dumps({"lineage": [{"id": "a", "note": "XAUUSD run"}]}))
    reg = tmp_path / "hypothesis_registry.json"
    reg.write_text(json.dumps({"hypotheses": [{"trial_number": 1001, "instrument": "XAUUSD"}]}))
    other = tmp_path / "hypothesis_registry_b.json"
    other.write_text(json.dumps({"hypotheses": [{"trial_number": 2001, "instrument": "BTCUSD"}]}))

    results = invalidate_symbol(
        "XAUUSD",
        reason="cost drift PSI=0.42",
        audit_ref="audit-3",
        trial_ledger_path=ledger,
        research_dir=tmp_path,
    )
    assert results["trial_ledger_marked"] == 1
    assert results["hypothesis_entries_marked"] == 1
    assert len(results["files_written"]) == 2  # ledger + registry.json, NOT _b

    # Unrelated registry untouched:
    assert json.loads(other.read_text(encoding="utf-8"))["hypotheses"][0].get("provenance_invalidated") is None
