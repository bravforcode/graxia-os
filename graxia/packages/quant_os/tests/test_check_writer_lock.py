# tests/test_check_writer_lock.py
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_writer_lock as cwl


@pytest.fixture
def lock_root(tmp_path):
    (tmp_path / ".writer.lock").write_text(
        json.dumps({"owner": "someone", "pid": 999999, "timestamp": 0.0}),
        encoding="utf-8",
    )
    return tmp_path


def test_pid_alive_false_for_dead_pid():
    assert cwl.pid_alive(999999) is False


def test_pid_alive_true_for_own_pid():
    assert cwl.pid_alive(os.getpid()) is True


def test_main_returns_0_when_no_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("WRITER_LOCK_ROOT", str(tmp_path))
    assert cwl.main() == 0


def test_main_returns_1_for_live_foreign_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("WRITER_LOCK_ROOT", str(tmp_path))
    (tmp_path / ".writer.lock").write_text(
        json.dumps({"owner": "other", "pid": os.getpid(), "timestamp": 0.0}),
        encoding="utf-8",
    )
    assert cwl.main() == 1


def test_main_returns_0_for_stale_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("WRITER_LOCK_ROOT", str(tmp_path))
    (tmp_path / ".writer.lock").write_text(
        json.dumps({"owner": "other", "pid": 999999, "timestamp": 0.0}),
        encoding="utf-8",
    )
    assert cwl.main() == 0


def test_main_returns_0_when_own_owner_env_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("WRITER_LOCK_ROOT", str(tmp_path))
    monkeypatch.setenv("WRITER_LOCK_OWNER", "my-session")
    (tmp_path / ".writer.lock").write_text(
        json.dumps({"owner": "my-session", "pid": os.getpid(), "timestamp": 0.0}),
        encoding="utf-8",
    )
    assert cwl.main() == 0


def test_main_returns_1_for_structurally_incomplete_lock(tmp_path, monkeypatch):
    # review finding #5: owner without pid (or invalid pid) must refuse, not fail-open
    monkeypatch.setenv("WRITER_LOCK_ROOT", str(tmp_path))
    (tmp_path / ".writer.lock").write_text(
        json.dumps({"owner": "other", "timestamp": 0.0}),
        encoding="utf-8",
    )
    assert cwl.main() == 1


def test_main_returns_1_for_invalid_pid_type(tmp_path, monkeypatch):
    # review finding #5: pid as string must refuse (structural check before liveness)
    monkeypatch.setenv("WRITER_LOCK_ROOT", str(tmp_path))
    (tmp_path / ".writer.lock").write_text(
        json.dumps({"owner": "other", "pid": "not-a-pid", "timestamp": 0.0}),
        encoding="utf-8",
    )
    assert cwl.main() == 1
