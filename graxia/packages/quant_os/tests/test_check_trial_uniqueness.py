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
        [{"trial_number": 1001, "id": "ONLY-ONE", "result": "PASS", "date": "2026-01-01"}],
    )
    monkeypatch.setattr(ctu, "RESEARCH_DIR", tmp_path)
    monkeypatch.setattr(ctu, "BASELINE", {})
    assert _run_main(monkeypatch, []) == 0


def test_new_collision_outside_baseline_exits_one(tmp_path, monkeypatch):
    _write_ledger(
        tmp_path / "trial_ledger.json",
        [{"trial_number": 1042, "id": "ALPHA", "result": "PASS", "date": "2026-01-01"}],
    )
    _write_registry(
        tmp_path / "hypothesis_registry.json",
        [{"trial_number": 1042, "id": "BETA", "status": "REJECTED"}],
    )
    monkeypatch.setattr(ctu, "RESEARCH_DIR", tmp_path)
    monkeypatch.setattr(ctu, "BASELINE", {})
    assert _run_main(monkeypatch, []) == 1


def test_collision_inside_baseline_exits_zero(tmp_path, monkeypatch):
    _write_ledger(
        tmp_path / "trial_ledger.json",
        [{"trial_number": 1042, "id": "ALPHA", "result": "PASS", "date": "2026-01-01"}],
    )
    _write_registry(
        tmp_path / "hypothesis_registry.json",
        [{"trial_number": 1042, "id": "BETA", "status": "REJECTED"}],
    )
    monkeypatch.setattr(ctu, "RESEARCH_DIR", tmp_path)
    monkeypatch.setattr(ctu, "BASELINE", {1042: "synthetic known collision for test"})
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


def test_baseline_is_empty_after_direction_c_renumber():
    """Direction C was renumbered off its collision with Direction B
    (3001-3003 -> 7001-7003, 2026-07-31) -- there is no more documented
    debt, so BASELINE should be empty. If someone adds an entry back here
    without a corresponding TRIAL_ID_RANGES.md write-up, this test forces
    an intentional edit rather than silently accepting new debt.
    """
    assert {} == ctu.BASELINE


def test_scan_pre_registration_docs_extracts_number_slug_family(tmp_path):
    doc_dir = tmp_path / "pre_registration_x"
    doc_dir.mkdir()
    (doc_dir / "trial_42_foo_bar.md").write_text("body", encoding="utf-8")
    (doc_dir / "template.md").write_text("not numbered", encoding="utf-8")
    entries = ctu.scan_pre_registration_docs(tmp_path)
    assert len(entries) == 1
    assert entries[0]["trial_number"] == 42
    assert entries[0]["slug"] == "foo_bar"
    assert entries[0]["family"] == "_x"


def test_check_doc_numbers_exist_flags_real_mismatch():
    """The #3001-vs-#3004 bug class: a doc's filename claims one number, but
    its family's ledger already recorded the same trial (matched by
    id/slug) under a different number.
    """
    doc_entries = [
        {
            "trial_number": 99,
            "slug": "alpha_strategy",
            "family": "_x",
            "source": "pre_registration_x/trial_99_alpha_strategy.md",
        }
    ]
    ledger_pairs = [("trial_ledger_x.json", [{"trial_number": 100, "id": "ALPHA-STRATEGY"}])]
    errors = ctu.check_doc_numbers_exist(doc_entries, ledger_pairs)
    assert len(errors) == 1
    assert "#99" in errors[0]
    assert "100" in errors[0]


def test_check_doc_numbers_exist_tolerates_pending_trial():
    """A pre-registered-but-not-yet-resulted trial (status: PENDING, no
    ledger/registry entry yet) must NOT be flagged -- that is the normal
    lifecycle, not the #3001-vs-#3004 bug. Regression guard for the real
    false positive hit during development: research/pre_registration/
    trial_1030_diversified_tsmom.md (status PENDING) has no ledger entry
    yet and must pass cleanly.
    """
    doc_entries = [
        {
            "trial_number": 1030,
            "slug": "diversified_tsmom",
            "family": "",
            "source": "pre_registration/trial_1030_diversified_tsmom.md",
        }
    ]
    ledger_pairs = [("trial_ledger.json", [{"trial_number": 1, "id": "SOMETHING-UNRELATED"}])]
    assert ctu.check_doc_numbers_exist(doc_entries, ledger_pairs) == []


def test_real_pre_registration_docs_pass_doc_number_check():
    """End-to-end regression guard for the Direction C renumber done in this
    commit (3001-3003 -> 7001-7003): every real pre_registration*/
    trial_NNNN_*.md doc must pass against the real ledger/registry data.
    """
    doc_entries = ctu.scan_pre_registration_docs(ctu.RESEARCH_DIR)
    assert len(doc_entries) >= 10  # sanity: docs are actually being found
    ledger_pairs = []
    for p in sorted(ctu.RESEARCH_DIR.glob("trial_ledger*.json")):
        ledger_pairs.append((p.name, ctu.load_ledger(p)))
    for p in sorted(ctu.RESEARCH_DIR.glob("hypothesis_registry*.json")):
        ledger_pairs.append((p.name, ctu.load_registry(p)))
    assert ctu.check_doc_numbers_exist(doc_entries, ledger_pairs) == []


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


def test_range_ownership_flag_outside_range(tmp_path, monkeypatch):
    """B2: a trial_number outside its family's owned range must be flagged."""
    from quant_os.scripts.check_trial_uniqueness import (
        FAMILY_RANGES,
        check_family_range_ownership,
    )

    # Direction D owns 4000-4999; a 3001 in registry_d is out of range.
    # Keys follow trial_family()'s output: suffixed files use '_d' (not 'd').
    assert FAMILY_RANGES["_d"] == (4000, 4999)
    entries = [{"trial_number": 3001, "id": "SOMETHING", "source": "hypothesis_registry_d.json", "result": "REJECT"}]
    errors = check_family_range_ownership([("hypothesis_registry_d.json", entries)])
    assert any("3001" in e and "range" in e for e in errors)
