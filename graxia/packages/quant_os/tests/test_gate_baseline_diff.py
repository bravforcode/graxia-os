"""Regression tests for Stream E guardrail of the audit-reconciliation spec:
summary.json baseline_diff + RE-BASELINE DETECTED print in the release gate.

Spec: docs/superpowers/specs/2026-08-03-audit-reconciliation-design.md section 7.
Edge case E8: guardrail verified by unit tests; no 20-min full gate run needed.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE_SCRIPT = ROOT / "scripts" / "run_release_gate.py"

# Load the gate script as a module without executing main().
_spec = importlib.util.spec_from_file_location("run_release_gate", GATE_SCRIPT)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def _stats(passed, skipped):
    return {"passed": passed, "failed": 0, "errors": 0, "skipped": skipped, "xfailed": 0, "xpassed": 0}


def test_no_previous_summary_yields_no_diff():
    diff, msg = gate.compute_baseline_diff(_stats(3462, 60), None)
    assert diff is None
    assert msg is None


def test_identical_counts_no_rebaseline_message():
    prev = {"run_a": {"stats": _stats(3462, 60)}}
    diff, msg = gate.compute_baseline_diff(_stats(3462, 60), prev)
    assert diff == {
        "passed_delta": 0,
        "skipped_delta": 0,
        "previous_passed": 3462,
        "previous_skipped": 60,
    }
    assert msg is None


def test_drift_emits_rebaseline_message():
    prev = {"run_a": {"stats": _stats(3462, 60)}}
    diff, msg = gate.compute_baseline_diff(_stats(3475, 45), prev)
    assert diff["passed_delta"] == 13
    assert diff["skipped_delta"] == -15
    assert msg == ("RE-BASELINE DETECTED: passed +13 / skipped -15 vs previous run " "(was 3462 passed / 60 skipped)")


def test_previous_stats_missing_is_tolerated():
    prev = {"run_a": {}}
    diff, msg = gate.compute_baseline_diff(_stats(3462, 60), prev)
    assert diff["passed_delta"] == 3462
    assert diff["skipped_delta"] == 60
    assert msg is not None
