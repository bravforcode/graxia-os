"""Verify quarantine manifest is consistent with actual test state."""
import json
from pathlib import Path

MANIFEST = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os\quarantine_manifest.json")
TESTS_DIR = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os\tests")


def test_quarantine_manifest_exists():
    """Quarantine manifest must exist."""
    assert MANIFEST.exists(), "quarantine_manifest.json missing"


def test_quarantine_manifest_valid_json():
    """Manifest must be valid JSON."""
    data = json.loads(MANIFEST.read_text())
    assert "quarantined_tests" in data


def test_quarantined_tests_have_required_fields():
    """Each quarantined test must have required fields."""
    data = json.loads(MANIFEST.read_text())
    required = ["test_file", "reason", "quarantined_at", "expiry", "release_impact"]
    for entry in data["quarantined_tests"]:
        for field in required:
            assert field in entry, f"Missing {field} in {entry.get('test_file', '?')}"


def test_quarantined_test_file_exists():
    """Each quarantined test file must exist."""
    data = json.loads(MANIFEST.read_text())
    for entry in data["quarantined_tests"]:
        path = TESTS_DIR / entry["test_file"].replace("tests/", "")
        assert path.exists(), f"Quarantined file missing: {path}"


def test_no_expired_quarantines():
    """No quarantine should be expired."""
    from datetime import date
    data = json.loads(MANIFEST.read_text())
    today = date.today().isoformat()
    for entry in data["quarantined_tests"]:
        assert entry["expiry"] >= today, (
            f"Expired quarantine: {entry['test_file']} expired {entry['expiry']}"
        )
