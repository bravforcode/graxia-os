"""Tests for scripts/check_trial_uniqueness.py's ratchet behavior.

Covers the guarantee the ratchet claims to make (fail on any NEW collision,
pass on documented BASELINE debt) both against synthetic fixtures and
against the real repo data, so a future edit that silently loosens BASELINE
or reintroduces a collision gets caught.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_trial_uniqueness.py"

_spec = importlib.util.spec_from_file_location("check_trial_uniqueness", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
ctu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ctu)


def _write_ledger(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps({"lineage": entries}), encoding="utf-8")


def _write_registry(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps({"hypotheses": entries}), encoding="utf-8")


def _run_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    """Run main() and return its effective process exit code. --list/--census
    return None (bare `return`) rather than calling sys.exit(0) -- both are
    exit code 0 when run as `python script.py`, so treat them the same here.
    """
    monkeypatch.setattr(sys, "argv", ["check_trial_uniqueness.py", *argv])
    try:
        ctu.main()
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0
    return 0


def test_no_collisions_exits_zero(tmp_path, monkeypatch):
    _write_ledger(
        tmp_path / "trial_ledger.json",
        [{"trial_number": 1, "id": "ONLY-ONE", "result": "PASS", "date": "2026-01-01"}],
    )
    monkeypatch.setattr(ctu, "RESEARCH_DIR", tmp_path)
    monkeypatch.setattr(ctu, "BASELINE", {})
    assert _run_main(monkeypatch, []) == 0


def test_new_collision_outside_baseline_exits_one(tmp_path, monkeypatch):
    _write_ledger(
        tmp_path / "trial_ledger.json",
        [{"trial_number": 42, "id": "ALPHA", "result": "PASS", "date": "2026-01-01"}],
    )
    _write_registry(
        tmp_path / "hypothesis_registry.json",
        [{"trial_number": 42, "id": "BETA", "status": "REJECTED"}],
    )
    monkeypatch.setattr(ctu, "RESEARCH_DIR", tmp_path)
    monkeypatch.setattr(ctu, "BASELINE", {})
    assert _run_main(monkeypatch, []) == 1


def test_collision_inside_baseline_exits_zero(tmp_path, monkeypatch):
    _write_ledger(
        tmp_path / "trial_ledger.json",
        [{"trial_number": 42, "id": "ALPHA", "result": "PASS", "date": "2026-01-01"}],
    )
    _write_registry(
        tmp_path / "hypothesis_registry.json",
        [{"trial_number": 42, "id": "BETA", "status": "REJECTED"}],
    )
    monkeypatch.setattr(ctu, "RESEARCH_DIR", tmp_path)
    monkeypatch.setattr(ctu, "BASELINE", {42: "synthetic known collision for test"})
    assert _run_main(monkeypatch, []) == 0


def test_list_flag_exits_zero_without_scanning(tmp_path, monkeypatch):
    monkeypatch.setattr(ctu, "RESEARCH_DIR", tmp_path)
    assert _run_main(monkeypatch, ["--list"]) == 0


def test_census_flag_exits_zero(tmp_path, monkeypatch):
    _write_ledger(
        tmp_path / "trial_ledger.json",
        [{"trial_number": 1, "id": "X", "result": "PASS", "date": "2026-01-01"}],
    )
    monkeypatch.setattr(ctu, "RESEARCH_DIR", tmp_path)
    assert _run_main(monkeypatch, ["--census"]) == 0


def test_real_repo_data_has_only_documented_baseline_collisions(monkeypatch):
    """Regression guard: today's real research/ data must exit 0 (no NEW
    collisions) and the only collisions present must be exactly BASELINE's
    keys -- if someone edits trial_ledger*.json/hypothesis_registry*.json
    and introduces a fresh collision, or silently drops a real BASELINE
    debt entry without fixing the data, this must fail.
    """
    assert _run_main(monkeypatch, []) == 0


def test_baseline_keys_are_the_known_direction_b_c_range():
    assert set(ctu.BASELINE.keys()) == {3001, 3002, 3003, 3004}


def test_load_ledger_extracts_mechanism_field(tmp_path):
    """Regression guard for the loader silently dropping a real 'mechanism'
    value on both the trial_number and trial_range entry shapes.
    """
    path = tmp_path / "trial_ledger.json"
    _write_ledger(
        path,
        [
            {"trial_number": 1, "id": "A", "mechanism": "real mechanism text"},
            {"trial_range": "2-5", "id": "B", "mechanism": "batch mechanism text"},
        ],
    )
    entries = ctu.load_ledger(path)
    assert entries[0]["mechanism"] == "real mechanism text"
    assert entries[1]["mechanism"] == "batch mechanism text"


def test_load_ledger_on_real_trial_ledger_c_has_all_three_mechanisms():
    """trial_ledger_c.json genuinely carries 'mechanism' on all 3 of its
    entries (crypto_volume_price_divergence, crypto_volatility_confirmation,
    crypto_pair_vol_spread) -- verified by grep. If the loader regresses to
    dropping the field again, this must fail.
    """
    path = ctu.RESEARCH_DIR / "trial_ledger_c.json"
    entries = ctu.load_ledger(path)
    mechanisms = [e["mechanism"] for e in entries if e.get("mechanism")]
    assert len(mechanisms) == 3


def test_mechanism_check_passes_for_entries_that_have_real_data():
    """check_mechanism() must not flag entries that genuinely have a
    non-empty 'mechanism' value once the loader passes it through.
    """
    entries = ctu.load_ledger(ctu.RESEARCH_DIR / "trial_ledger_c.json")
    errors = ctu.check_mechanism(entries)
    assert errors == []
