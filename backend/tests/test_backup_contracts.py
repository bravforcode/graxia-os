import hashlib
import subprocess
from pathlib import Path

import pytest
from scripts.backup_database import BackupManifest, DatabaseBackup, compute_sha256
from scripts.restore_database import DatabaseRestore


def test_backup_manifest_preserves_plain_and_encrypted_checksums(tmp_path: Path):
    dump = tmp_path / "backup.dump"
    encrypted = tmp_path / "backup.dump.age"
    dump.write_bytes(b"plain backup payload")
    encrypted.write_bytes(b"encrypted backup payload")

    manifest = BackupManifest(
        backup_id="backup-1",
        environment="test",
        git_sha="abc1234",
        artifact_name=encrypted.name,
        artifact_type="postgres",
        created_at="2026-04-11T00:00:00+00:00",
        size_bytes=encrypted.stat().st_size,
        checksum_plaintext=compute_sha256(dump),
        checksum_encrypted=compute_sha256(encrypted),
        postgres_version="postgres (PostgreSQL) 16.3",
        migration_version="head",
        encryption="age",
        retention_tier="daily",
    )

    manifest_path = tmp_path / "backup.manifest.json"
    manifest.write_json(manifest_path)

    loaded = BackupManifest.from_json(manifest_path)
    assert loaded.checksum_plaintext == hashlib.sha256(b"plain backup payload").hexdigest()
    assert loaded.checksum_encrypted == hashlib.sha256(b"encrypted backup payload").hexdigest()
    assert loaded.encryption == "age"


def test_database_backup_creates_age_encrypted_artifact_and_manifest(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("scripts.backup_database.settings.BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(
        "scripts.backup_database.settings.DATABASE_URL",
        "postgresql+asyncpg://user:password@postgres:5432/personal_os",
    )
    monkeypatch.setattr("scripts.backup_database.settings.BACKUP_ENCRYPTION_PUBLIC_KEY", "age1test")
    monkeypatch.setattr("scripts.backup_database.settings.BACKUP_BUCKET", "")
    monkeypatch.setattr("scripts.backup_database.settings.APP_ENV", "test")

    commands: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        commands.append(list(cmd))
        if cmd[0] == "pg_dump":
            Path(cmd[cmd.index("--file") + 1]).write_bytes(b"PGDMP custom format")
        elif cmd[0] == "age":
            Path(cmd[cmd.index("--output") + 1]).write_bytes(b"age encrypted payload")
        elif cmd[0] == "pg_config":
            return subprocess.CompletedProcess(cmd, 0, stdout="PostgreSQL 16.3\n", stderr="")
        elif cmd[0] == "git":
            return subprocess.CompletedProcess(cmd, 0, stdout="abcdef0\n", stderr="")
        else:
            raise AssertionError(f"unexpected command: {cmd}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("scripts.backup_database.subprocess.run", fake_run)

    result = DatabaseBackup().create_backup()

    assert result.artifact_path.name.endswith(".dump.age")
    assert result.artifact_path.exists()
    assert result.manifest_path.exists()
    assert result.manifest.checksum_plaintext == hashlib.sha256(b"PGDMP custom format").hexdigest()
    assert (
        result.manifest.checksum_encrypted == hashlib.sha256(b"age encrypted payload").hexdigest()
    )
    assert any(cmd[0] == "age" and "--recipient" in cmd for cmd in commands)
    assert any(cmd[0] == "pg_dump" and "-F" in cmd and "c" in cmd for cmd in commands)


def test_restore_refuses_encrypted_backup_without_private_key(tmp_path: Path, monkeypatch):
    encrypted = tmp_path / "backup.dump.age"
    encrypted.write_bytes(b"encrypted payload")
    manifest = BackupManifest(
        backup_id="backup-1",
        environment="test",
        git_sha="abc1234",
        artifact_name=encrypted.name,
        artifact_type="postgres",
        created_at="2026-04-11T00:00:00+00:00",
        size_bytes=encrypted.stat().st_size,
        checksum_plaintext=hashlib.sha256(b"plain payload").hexdigest(),
        checksum_encrypted=compute_sha256(encrypted),
        postgres_version="postgres (PostgreSQL) 16.3",
        migration_version="head",
        encryption="age",
        retention_tier="daily",
    )

    monkeypatch.setattr(
        "scripts.restore_database.settings.BACKUP_ENCRYPTION_PRIVATE_KEY_FILE",
        str(tmp_path / "missing-key.txt"),
    )

    with pytest.raises(RuntimeError, match="decryption key"):
        DatabaseRestore().prepare_backup_for_restore(encrypted, manifest, work_dir=tmp_path)


def test_restore_decrypts_and_verifies_plaintext_checksum(tmp_path: Path, monkeypatch):
    encrypted = tmp_path / "backup.dump.age"
    encrypted.write_bytes(b"encrypted payload")
    key_file = tmp_path / "age-key.txt"
    key_file.write_text("AGE-SECRET-KEY-test", encoding="utf-8")
    plaintext_payload = b"PGDMP restored payload"
    manifest = BackupManifest(
        backup_id="backup-1",
        environment="test",
        git_sha="abc1234",
        artifact_name=encrypted.name,
        artifact_type="postgres",
        created_at="2026-04-11T00:00:00+00:00",
        size_bytes=encrypted.stat().st_size,
        checksum_plaintext=hashlib.sha256(plaintext_payload).hexdigest(),
        checksum_encrypted=compute_sha256(encrypted),
        postgres_version="postgres (PostgreSQL) 16.3",
        migration_version="head",
        encryption="age",
        retention_tier="daily",
    )

    def fake_run(cmd, **kwargs):
        assert cmd[0] == "age"
        Path(cmd[cmd.index("--output") + 1]).write_bytes(plaintext_payload)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(
        "scripts.restore_database.settings.BACKUP_ENCRYPTION_PRIVATE_KEY_FILE", str(key_file)
    )
    monkeypatch.setattr("scripts.restore_database.subprocess.run", fake_run)

    restored_dump = DatabaseRestore().prepare_backup_for_restore(
        encrypted, manifest, work_dir=tmp_path
    )

    assert restored_dump.read_bytes() == plaintext_payload
