"""Tests for quarantine_manager."""
import json
from pathlib import Path

from graxia.packages.quant_os.quarantine_manager import QuarantineEntry, QuarantineManager

# Use local temp dir to avoid Windows permission issues with system temp
_LOCAL_TEMP = Path(__file__).parent / ".test_tmp"
_LOCAL_TEMP.mkdir(exist_ok=True)


def _entry(test_id="test_alpha", reason="flaky", owner="alice", issue_id="ISS-001", expiry="2026-12-31"):
    return QuarantineEntry(
        test_id=test_id,
        reason=reason,
        owner=owner,
        issue_id=issue_id,
        expiry=expiry,
        created_at="2026-06-22T00:00:00",
    )


def _qm_path(name="q.json"):
    return str(_LOCAL_TEMP / name)


def test_quarantine_add_entry():
    mgr = QuarantineManager(_qm_path("add.json"))
    entry = _entry()
    mgr.add(entry)
    assert mgr.count() == 1
    assert mgr.is_quarantined("test_alpha")
    assert mgr.get_entry("test_alpha")["signature"] != ""


def test_quarantine_remove_entry():
    mgr = QuarantineManager(_qm_path("remove.json"))
    mgr.add(_entry())
    assert mgr.remove("test_alpha") is True
    assert mgr.count() == 0
    assert mgr.remove("test_alpha") is False


def test_quarantine_is_quarantined():
    mgr = QuarantineManager(_qm_path("check.json"))
    assert mgr.is_quarantined("nope") is False
    mgr.add(_entry())
    assert mgr.is_quarantined("test_alpha") is True


def test_quarantine_integrity():
    path = Path(_qm_path("integrity.json"))
    mgr = QuarantineManager(str(path))
    mgr.add(_entry())
    ok, msg = mgr.verify_integrity()
    assert ok is True
    assert msg == "OK"

    # Tamper with manifest
    data = json.loads(path.read_text())
    data["entries"][0]["test_id"] = "tampered"
    path.write_text(json.dumps(data, indent=2))
    ok2, msg2 = mgr.verify_integrity()
    assert ok2 is False
    assert "hash_mismatch" in msg2


def test_quarantine_list_entries():
    mgr = QuarantineManager(_qm_path("list.json"))
    mgr.add(_entry())
    mgr.add(_entry(test_id="test_beta", owner="bob"))
    entries = mgr.list_entries()
    assert len(entries) == 2
    ids = {e["test_id"] for e in entries}
    assert ids == {"test_alpha", "test_beta"}
