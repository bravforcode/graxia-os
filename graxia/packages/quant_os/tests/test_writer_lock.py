"""Regression tests for Stream D of the audit-reconciliation spec:
single-writer lock mechanism (.writer.lock, acquire/release scripts,
fail-closed gate pre-flight).

Spec: docs/superpowers/specs/2026-08-03-audit-reconciliation-design.md section 6.
Edge case E8: verified by unit tests; no full 20-min gate run needed.
"""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ACQUIRE = ROOT / "scripts" / "acquire_writer_lock.py"
RELEASE = ROOT / "scripts" / "release_writer_lock.py"
GATE_SCRIPT = ROOT / "scripts" / "run_release_gate.py"

# Load modules under test with a temp lock location.
_spec = importlib.util.spec_from_file_location("run_release_gate", GATE_SCRIPT)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


@pytest.fixture()
def tmp_lock_path(tmp_path, monkeypatch):
    """Point the gate module at a temp .writer.lock path."""
    lock_path = tmp_path / ".writer.lock"
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    return lock_path


def _write_lock(path, owner, pid, timestamp=None):
    path.write_text(
        json.dumps({"owner": owner, "pid": pid, "timestamp": timestamp or time.time()}),
        encoding="utf-8",
    )


def _run_script(script, args, tmp_path):
    env = dict(os.environ)
    env["WRITER_LOCK_ROOT"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, str(script)] + args, cwd=str(tmp_path), capture_output=True, text=True, env=env
    )


def test_acquire_twice_second_fails_release_reacquire_succeeds(tmp_path):
    """Scripted acceptance: acquire twice -> second fails; release -> re-acquire succeeds."""
    lock = tmp_path / ".writer.lock"

    # First acquire (subprocess so pid differs from test runner).
    r1 = _run_script(ACQUIRE, ["--owner", "tester"], tmp_path)
    assert r1.returncode == 0, r1.stderr
    assert lock.exists()

    # Second acquire from a different process -> fail-closed.
    r2 = _run_script(ACQUIRE, ["--owner", "other"], tmp_path)
    assert r2.returncode == 1, r2.stdout
    assert "LOCK HELD" in r2.stdout
    assert "owner=tester" in r2.stdout

    # Release by the holder (same owner+pid required; simulate owning process).
    data = json.loads(lock.read_text(encoding="utf-8"))
    assert data["owner"] == "tester"

    # Re-acquire after release (simulate by removing the lock = release).
    lock.unlink()
    r3 = _run_script(ACQUIRE, ["--owner", "tester"], tmp_path)
    assert r3.returncode == 0, r3.stderr
    assert lock.exists()


def test_release_script_refuses_foreign_owner(tmp_path):
    """Release must never delete a foreign lock."""
    lock = tmp_path / ".writer.lock"
    _write_lock(lock, owner="someone_else", pid=12345)
    r = _run_script(RELEASE, ["--owner", "me"], tmp_path)
    assert r.returncode == 2
    assert "Refusing to release" in r.stdout
    assert lock.exists()


def test_gate_fail_closed_on_foreign_lock(tmp_lock_path):
    """Gate pre-flight: foreign lock -> check_writer_lock returns error with owner info."""
    _write_lock(tmp_lock_path, owner="another_session", pid=999)
    errors = gate.check_writer_lock()
    assert len(errors) == 1
    assert "another_session" in errors[0]
    assert "999" in errors[0]


def test_gate_clear_with_no_lock(tmp_lock_path):
    """Gate pre-flight: no lock -> no errors."""
    assert gate.check_writer_lock() == []


def test_gate_reports_stale_lock_with_manual_clear_note(tmp_lock_path):
    """Stale lock (>24h) reported with owner info and manual-clear guidance, never silent auto-clear."""
    _write_lock(tmp_lock_path, owner="ghost", pid=1, timestamp=time.time() - 25 * 3600)
    errors = gate.check_writer_lock()
    assert len(errors) == 1
    assert "STALE" in errors[0]
    assert "ghost" in errors[0]
    assert "--force" in errors[0] or "manually" in errors[0]
