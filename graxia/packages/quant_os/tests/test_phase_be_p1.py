"""Phase BE-P1 integration tests — release truth reconciliation."""
import json
from pathlib import Path
from graxia.packages.quant_os.quarantine_manager import QuarantineManager, QuarantineEntry
from graxia.packages.quant_os.scripts.release_gate import ReleaseGate


def test_release_gate_exists():
    """ReleaseGate must exist."""
    gate = ReleaseGate(".")
    assert gate is not None


def test_release_gate_checks():
    """ReleaseGate must have required checks."""
    gate = ReleaseGate(".")
    assert hasattr(gate, "check_clean_worktree")
    assert hasattr(gate, "check_test_suite")
    assert hasattr(gate, "check_no_unapproved_skips")
    assert hasattr(gate, "check_quarantine_manifest")
    assert hasattr(gate, "check_git_commit")


def test_quarantine_manager_exists():
    """QuarantineManager must exist."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        json.dump({"entries": []}, f)
        f.flush()
        qm = QuarantineManager(f.name)
        assert qm is not None


def test_quarantine_add_and_verify():
    """QuarantineManager must add and verify entries."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        json.dump({"entries": []}, f)
        f.flush()
        qm = QuarantineManager(f.name)
        entry = QuarantineEntry(
            test_id="test_vwap",
            reason="DEPRECATED: data format mismatch",
            owner="system",
            issue_id="N/A",
            expiry="2026-12-31",
            created_at="2026-06-22",
        )
        qm.add(entry)
        assert qm.is_quarantined("test_vwap")
        assert qm.count() == 1
        ok, msg = qm.verify_integrity()
        assert ok


def test_data_manifest_hashes_exist():
    """Data manifest hashes script must exist."""
    script = Path(__file__).parent.parent / "scripts" / "hash_data_manifests.py"
    assert script.exists()


def test_release_truth_script_exists():
    """Release truth runner script must exist."""
    script = Path(__file__).parent.parent / "scripts" / "run_release_truth.py"
    assert script.exists()


def test_verify_reproducibility_exists():
    """Verify reproducibility script must exist."""
    script = Path(__file__).parent.parent / "scripts" / "verify_reproducibility.py"
    assert script.exists()
