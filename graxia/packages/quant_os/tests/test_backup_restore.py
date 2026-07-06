"""Tests for backup/restore infrastructure."""

import json
import shutil
import sys
from pathlib import Path

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from backup_state import backup_state, collect_state_files, get_backup_dir_name, rotate_backups
from restore_state import find_backup, list_backups, restore_from_backup, validate_backup


@pytest.fixture(autouse=True)
def _setup_teardown(tmp_path, monkeypatch):
    """Set up temp dirs and clean up after."""
    # Clear logger handlers to avoid Windows file lock issues
    import backup_state

    backup_state.logger.handlers.clear()
    backup_state._file_handler_added = False

    # Create temp data/state dirs with test content
    data_dir = tmp_path / "data"
    state_dir = tmp_path / "state"
    data_dir.mkdir()
    state_dir.mkdir()

    # Write test state files
    (data_dir / "kill_switch_state.json").write_text(json.dumps({"state": "INACTIVE"}))
    (data_dir / "circuit_breaker_state.json").write_text(json.dumps({"classes": {}}))
    (data_dir / "risk_ledger.json").write_text(json.dumps({"daily_realized_loss": 0.0}))
    (data_dir / "auto_stop_state.json").write_text(json.dumps({"triggered": False}))
    (data_dir / "risk_overlay_state.json").write_text(json.dumps({"kill_switch_triggered": False}))
    (data_dir / "execution_ledger.jsonl").write_text('{"trade": 1}\n')
    (state_dir / "system_state.json").write_text(json.dumps({"system_state": "RUNNING"}))

    # Patch PROJECT_ROOT and related paths
    monkeypatch.setattr("backup_state.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("backup_state.BACKUP_ROOT", tmp_path / "backups")
    monkeypatch.setattr("backup_state.LOG_FILE", tmp_path / "backups" / "backup.log")
    monkeypatch.setattr("restore_state.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("restore_state.BACKUP_ROOT", tmp_path / "backups")

    yield tmp_path

    # Cleanup - clear logger handlers first to release file locks
    backup_state.logger.handlers.clear()
    backup_state._file_handler_added = False

    if (tmp_path / "backups").exists():
        shutil.rmtree(str(tmp_path / "backups"), ignore_errors=True)


class TestBackupState:
    def test_collect_state_files(self):
        """All state files are found when they exist."""
        files = collect_state_files()
        names = [f.name for f in files]
        assert "kill_switch_state.json" in names
        assert "circuit_breaker_state.json" in names
        assert "risk_ledger.json" in names
        assert "auto_stop_state.json" in names
        assert "risk_overlay_state.json" in names
        assert "execution_ledger.jsonl" in names
        assert "system_state.json" in names

    def test_collect_state_files_missing(self, tmp_path, monkeypatch):
        """Missing files are silently skipped."""
        empty_dir = tmp_path / "empty_project"
        empty_dir.mkdir()
        monkeypatch.setattr("backup_state.PROJECT_ROOT", empty_dir)
        # data dir has no files - should return empty
        files = collect_state_files()
        assert len(files) == 0

    def test_backup_creates_directory(self):
        """Backup creates a date-stamped directory."""
        result = backup_state()
        assert result["status"] == "success"
        assert result["files"] >= 6
        backup_dir = Path(result["backup_dir"])
        assert backup_dir.exists()
        assert (backup_dir / "manifest.json").exists()

    def test_backup_dry_run(self):
        """Dry run doesn't create files."""
        result = backup_state(dry_run=True)
        assert result["status"] == "dry_run"
        # Backup dir should not exist yet
        assert not Path(result["backup_dir"]).exists()

    def test_backup_manifest_content(self):
        """Manifest contains expected fields."""
        result = backup_state()
        manifest_path = Path(result["backup_dir"]) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "timestamp" in manifest
        assert "created_at" in manifest
        assert "files_backed_up" in manifest
        assert "state_files_found" in manifest
        assert len(manifest["state_files_found"]) >= 6

    def test_backup_preserves_content(self):
        """Backed up files have correct content."""
        result = backup_state()
        backup_dir = Path(result["backup_dir"])

        # Check kill switch state
        ks = json.loads((backup_dir / "data" / "kill_switch_state.json").read_text(encoding="utf-8"))
        assert ks["state"] == "INACTIVE"

        # Check system state
        ss = json.loads((backup_dir / "state" / "system_state.json").read_text(encoding="utf-8"))
        assert ss["system_state"] == "RUNNING"

    def test_rotate_backups(self, tmp_path, monkeypatch):
        """Old backups are rotated."""
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()

        # Create fake old backup (10 days ago)
        old_dir = backups_dir / "2026-06-20_120000"
        old_dir.mkdir()
        (old_dir / "manifest.json").write_text("{}")

        # Create fake recent backup
        recent_dir = backups_dir / get_backup_dir_name()
        recent_dir.mkdir()
        (recent_dir / "manifest.json").write_text("{}")

        monkeypatch.setattr("backup_state.BACKUP_ROOT", backups_dir)
        removed = rotate_backups(keep_days=7)
        assert removed == 1
        assert not old_dir.exists()
        assert recent_dir.exists()

    def test_get_backup_dir_name_format(self):
        """Backup dir name has correct format."""
        name = get_backup_dir_name()
        # Format: YYYY-MM-DD_HHMMSS (17 chars, no separators in time)
        assert len(name) == 17
        assert name[4] == "-"
        assert name[7] == "-"
        assert name[10] == "_"
        # Time portion should be digits only (HHMMSS)
        assert name[11:].isdigit()
        assert len(name[11:]) == 6


class TestRestoreState:
    def test_list_backups(self):
        """Lists backups after creating one."""
        backup_state()
        backups = list_backups()
        assert len(backups) == 1
        assert backups[0]["files_backed_up"] >= 6

    def test_list_backups_empty(self):
        """Empty list when no backups exist."""
        backups = list_backups()
        assert len(backups) == 0

    def test_find_backup_exact(self):
        """Find backup by exact directory name."""
        result = backup_state()
        dir_name = Path(result["backup_dir"]).name
        found = find_backup(dir_name)
        assert found is not None
        assert found.name == dir_name

    def test_find_backup_date_prefix(self):
        """Find backup by date prefix."""
        result = backup_state()
        dir_name = Path(result["backup_dir"]).name
        date_prefix = dir_name[:10]  # YYYY-MM-DD
        found = find_backup(date_prefix)
        assert found is not None

    def test_find_backup_not_found(self):
        """Returns None for non-existent backup."""
        found = find_backup("2099-01-01_000000")
        assert found is None

    def test_validate_backup_valid(self):
        """Valid backup passes validation."""
        result = backup_state()
        backup_dir = Path(result["backup_dir"])
        validation = validate_backup(backup_dir)
        assert validation["valid"] is True
        assert len(validation["issues"]) == 0

    def test_validate_backup_missing_manifest(self, tmp_path):
        """Backup without manifest fails validation."""
        fake_dir = tmp_path / "backups" / "fake_dir"
        fake_dir.mkdir(parents=True)
        validation = validate_backup(fake_dir)
        assert validation["valid"] is False
        assert any("manifest" in i.lower() for i in validation["issues"])

    def test_restore_success(self, tmp_path):
        """Restore recreates all state files."""
        result = backup_state()
        backup_dir = Path(result["backup_dir"])

        # Remove original data
        shutil.rmtree(str(tmp_path / "data"))
        shutil.rmtree(str(tmp_path / "state"))

        # Restore
        restore_result = restore_from_backup(backup_dir)
        assert restore_result["status"] == "success"
        assert restore_result["restored"] >= 6

        # Verify files exist and have correct content
        assert (tmp_path / "data" / "kill_switch_state.json").exists()
        assert (tmp_path / "state" / "system_state.json").exists()

        ks = json.loads((tmp_path / "data" / "kill_switch_state.json").read_text(encoding="utf-8"))
        assert ks["state"] == "INACTIVE"

    def test_restore_dry_run(self, tmp_path):
        """Dry run doesn't modify files."""
        result = backup_state()
        backup_dir = Path(result["backup_dir"])

        # Remove original data
        shutil.rmtree(str(tmp_path / "data"))
        shutil.rmtree(str(tmp_path / "state"))

        # Dry run restore
        restore_result = restore_from_backup(backup_dir, dry_run=True)
        assert restore_result["status"] == "success"

        # Files should NOT exist
        assert not (tmp_path / "data" / "kill_switch_state.json").exists()

    def test_restore_from_latest(self):
        """Restore using list + latest flow."""
        # Create two backups
        backup_state()
        import time

        time.sleep(1.1)  # ensure different timestamp
        backup_state()

        backups = list_backups()
        assert len(backups) == 2

        # Restore from latest
        latest = find_backup(backups[0]["dir_name"])
        result = restore_from_backup(latest)
        assert result["status"] == "success"


class TestBackupRestoreRoundTrip:
    def test_full_round_trip(self, tmp_path):
        """Full backup → modify → restore round trip."""
        # 1. Backup original state
        result = backup_state()
        backup_dir = Path(result["backup_dir"])

        # 2. Modify state files
        ks_path = tmp_path / "data" / "kill_switch_state.json"
        ks_path.write_text(json.dumps({"state": "ACTIVE"}))
        assert json.loads(ks_path.read_text(encoding="utf-8"))["state"] == "ACTIVE"

        # 3. Restore from backup
        restore_result = restore_from_backup(backup_dir)
        assert restore_result["status"] == "success"

        # 4. Verify state is restored to original
        ks = json.loads(ks_path.read_text(encoding="utf-8"))
        assert ks["state"] == "INACTIVE"

    def test_multiple_backups(self):
        """Multiple backups create separate directories."""
        result1 = backup_state()
        import time

        time.sleep(1.1)
        result2 = backup_state()

        dir1 = Path(result1["backup_dir"])
        dir2 = Path(result2["backup_dir"])
        assert dir1 != dir2
        assert dir1.exists()
        assert dir2.exists()

        backups = list_backups()
        assert len(backups) == 2
