#!/usr/bin/env python3
"""Manifest-verified restore for encrypted PostgreSQL backups."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from scripts.backup_database import (
    BackupManifest,
    ObjectStore,
    compute_sha256,
    parse_database_url,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


class DatabaseRestore:
    """Restore age-encrypted pg_dump custom-format artifacts."""

    def __init__(self, database_url: str | None = None, object_store: ObjectStore | None = None):
        self.database_url = database_url or settings.DATABASE_URL
        self.connection = parse_database_url(self.database_url)
        self.object_store = object_store or ObjectStore()

    def prepare_backup_for_restore(
        self,
        encrypted_backup: Path,
        manifest: BackupManifest,
        *,
        work_dir: Path | None = None,
    ) -> Path:
        encrypted_backup = Path(encrypted_backup)
        work_dir = Path(work_dir or tempfile.mkdtemp(prefix="restore-"))
        work_dir.mkdir(parents=True, exist_ok=True)

        if manifest.encryption != "age":
            raise RuntimeError(f"Unsupported backup encryption: {manifest.encryption}")
        if compute_sha256(encrypted_backup) != manifest.checksum_encrypted:
            raise RuntimeError("Encrypted backup checksum mismatch")

        key_file = Path(settings.BACKUP_ENCRYPTION_PRIVATE_KEY_FILE or "")
        if not key_file.exists():
            raise RuntimeError("Backup decryption key is missing; restore cannot continue")

        output_path = work_dir / encrypted_backup.name.removesuffix(".age")
        cmd = [
            "age",
            "--decrypt",
            "--identity",
            str(key_file),
            "--output",
            str(output_path),
            str(encrypted_backup),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            raise RuntimeError(f"Backup decryption failed: {result.stderr.strip()}")

        actual_plaintext = compute_sha256(output_path)
        if actual_plaintext != manifest.checksum_plaintext:
            output_path.unlink(missing_ok=True)
            raise RuntimeError("Decrypted backup checksum mismatch")
        return output_path

    def restore_prepared_dump(self, dump_path: Path) -> None:
        env = os.environ.copy()
        env["PGPASSWORD"] = self.connection.password
        if self.connection.sslmode or self.connection.host.endswith("supabase.co"):
            env["PGSSLMODE"] = self.connection.sslmode or "require"
        cmd = [
            "pg_restore",
            "-h",
            self.connection.host,
            "-p",
            str(self.connection.port),
            "-U",
            self.connection.user,
            "-d",
            self.connection.database,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-acl",
            str(dump_path),
        ]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            raise RuntimeError(f"pg_restore failed: {result.stderr.strip()}")

    def restore_backup(
        self,
        encrypted_backup: Path,
        manifest: BackupManifest,
        *,
        work_dir: Path | None = None,
    ) -> Path:
        dump_path = self.prepare_backup_for_restore(encrypted_backup, manifest, work_dir=work_dir)
        self.restore_prepared_dump(dump_path)
        return dump_path

    def download_backup(self, artifact_key: str, manifest_key: str, work_dir: Path) -> tuple[Path, BackupManifest]:
        if not self.object_store.enabled():
            raise RuntimeError("BACKUP_BUCKET is not configured")
        import boto3

        kwargs = {}
        if settings.BACKUP_REGION:
            kwargs["region_name"] = settings.BACKUP_REGION
        if settings.BACKUP_ENDPOINT:
            kwargs["endpoint_url"] = settings.BACKUP_ENDPOINT
        client = boto3.client("s3", **kwargs)

        artifact_path = work_dir / Path(artifact_key).name
        manifest_path = work_dir / Path(manifest_key).name
        client.download_file(settings.BACKUP_BUCKET, artifact_key, str(artifact_path))
        client.download_file(settings.BACKUP_BUCKET, manifest_key, str(manifest_path))
        return artifact_path, BackupManifest.from_json(manifest_path)


def _load_manifest(path: Path) -> BackupManifest:
    if not path.exists():
        raise RuntimeError(f"Manifest file not found: {path}")
    return BackupManifest.from_json(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore an encrypted PostgreSQL backup")
    parser.add_argument("--backup-file", type=Path, help="Local .dump.age artifact")
    parser.add_argument("--manifest-file", type=Path, help="Local manifest JSON")
    parser.add_argument("--target-db", help="Override DATABASE_URL for restore target")
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--yes", action="store_true", help="Confirm destructive restore")
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("Refusing destructive restore without --yes")
    if not args.backup_file or not args.manifest_file:
        raise SystemExit("--backup-file and --manifest-file are required")

    manifest = _load_manifest(args.manifest_file)
    restore = DatabaseRestore(database_url=args.target_db)
    restored = restore.restore_backup(args.backup_file, manifest, work_dir=args.work_dir)
    logger.info("Restore completed from %s", restored)


if __name__ == "__main__":
    main()
