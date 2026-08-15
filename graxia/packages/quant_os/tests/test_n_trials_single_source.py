"""Regression tests for Stream C of the audit-reconciliation spec:
N for multiple-testing correction must come from the single canonical
source (validation/n_trials.py), never hardcoded literals.

Spec: docs/superpowers/specs/2026-08-03-audit-reconciliation-design.md section 5.
History: N drifted 4x in one conversation (1050 -> 1021 -> 1508 -> 1033);
record-fix alone failed, so a derived-single-source regression gate is required.
"""

import json
from pathlib import Path

from validation.n_trials import get_reconciled_n_trials

ROOT = Path(__file__).resolve().parent.parent
RECONCILIATION = ROOT / "reports" / "trial_count_reconciliation_20260720.json"
CHECK_CANDIDATE_DSR = ROOT / "scripts" / "check_candidate_dsr.py"


def test_n_trials_derived_from_reconciliation_artifact():
    """The derived N must equal the committed reconciliation artifact value."""
    data = json.loads(RECONCILIATION.read_text(encoding="utf-8"))
    expected = int(data["total_n_for_multiple_testing"])
    assert get_reconciled_n_trials() == expected


def test_check_candidate_dsr_imports_n_from_canonical_source():
    """check_candidate_dsr must derive N, not hardcode it."""
    source = CHECK_CANDIDATE_DSR.read_text(encoding="utf-8")
    assert "from validation.n_trials import get_reconciled_n_trials" in source
    assert "N_TRIALS = get_reconciled_n_trials()" in source


def test_no_hardcoded_stale_n_literal_in_scripts_or_validation():
    """Spec acceptance: grep -r '1508' scripts/ validation/ clean."""
    for subdir in ("scripts", "validation"):
        for path in (ROOT / subdir).rglob("*.py"):
            assert "1508" not in path.read_text(encoding="utf-8"), path
