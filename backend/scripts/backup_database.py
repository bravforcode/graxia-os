#!/usr/bin/env python3
"""Encrypted PostgreSQL and Redis backup helpers for production DR.

The PostgreSQL flow is intentionally non-interactive and manifest-driven:
pg_dump custom format -> plaintext checksum -> age encryption -> encrypted checksum
-> optional S3-compatible upload -> re-download verification.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


RETENTION_DAYS = 30


@dataclass(frozen=True)
class DatabaseConnection:
    host: str
    port: int
    user: str
    password: str
    database: str
    sslmode: str | None = None


@dataclass(frozen=True)
class BackupManifest:
    backup_id: str
    environment: str
    git_sha: str
    artifact_name: str
    artifact_type: str
    created_at: str
    size_bytes: int
    checksum_plaintext: str
    checksum_encrypted: str
    postgres_version: str
    migration_version: str
    encryption: str
    retention_tier: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def write_json(self, path: Path) -> None:
        path.write_text(self.to_json() + "\n", encoding="utf-8")

    @classmethod
    def from_json(cls, path: Path) -> "BackupManifest":
        return cls(**json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class BackupResult:
    artifact_path: Path
    manifest_path: Path
    manifest: BackupManifest
    uploaded: bool = False


def compute_sha256(path: Path) -> str:
    digest = hashlib_sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hashlib_sha256():
    import hashlib

    return hashlib.sha256()


def _sync_database_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def parse_database_url(database_url: str) -> DatabaseConnection:
    parsed = urlsplit(_sync_database_url(database_url))
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise ValueError("DATABASE_URL must use postgresql:// or postgresql+asyncpg://")
    if not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("DATABASE_URL must include host and database name")
    query = parse_qs(parsed.query)
    sslmode = (query.get("sslmode") or query.get("ssl") or [None])[0]
    return DatabaseConnection(
        host=parsed.hostname,
        port=parsed.port or 5432,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=unquote(parsed.path.strip("/")),
        sslmode=sslmode,
    )


def _run_command(cmd: list[str], *, env: dict[str, str] | None = None, timeout: int = 1800) -> subprocess.CompletedProcess:
    logger.debug("Running command: %s", " ".join(cmd[:2]))
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {result.stderr.strip()}")
    return result


def get_git_sha() -> str:
    try:
        result = _run_command(["git", "rev-parse", "--short=12", "HEAD"], timeout=10)
        return (result.stdout or "").strip() or "unknown"
    except Exception:
        return os.getenv("GIT_SHA", "unknown")[:12]


def get_postgres_version() -> str:
    try:
        result = _run_command(["pg_config", "--version"], timeout=10)
        return (result.stdout or "").strip() or "unknown"
    except Exception:
        return "unknown"


def get_current_migration_version() -> str:
    return os.getenv("MIGRATION_VERSION", "unknown")


def _s3_client():
    import boto3

    kwargs: dict[str, Any] = {}
    if settings.BACKUP_REGION:
        kwargs["region_name"] = settings.BACKUP_REGION
    if settings.BACKUP_ENDPOINT:
        kwargs["endpoint_url"] = settings.BACKUP_ENDPOINT
    return boto3.client("s3", **kwargs)


class ObjectStore:
    def __init__(self, bucket: str | None = None, prefix: str | None = None):
        self.bucket = bucket if bucket is not None else settings.BACKUP_BUCKET
        self.prefix = (prefix if prefix is not None else settings.BACKUP_PREFIX).strip("/")

    def enabled(self) -> bool:
        return bool((self.bucket or "").strip())

    def key_for(self, artifact_type: str, retention_tier: str, name: str) -> str:
        parts = [part for part in [self.prefix, artifact_type, retention_tier, name] if part]
        return "/".join(parts)

    def upload_and_verify(self, local_path: Path, key: str, metadata: dict[str, Any] | None = None) -> None:
        if not self.enabled():
            raise RuntimeError("BACKUP_BUCKET is not configured")

        client = _s3_client()
        extra_args: dict[str, Any] = {
            "ServerSideEncryption": "AES256",
            "Metadata": {str(k): str(v)[:1024] for k, v in (metadata or {}).items()},
        }
        client.upload_file(str(local_path), self.bucket, key, ExtraArgs=extra_args)

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            downloaded = Path(tmp.name)
        try:
            client.download_file(self.bucket, key, str(downloaded))
            if compute_sha256(downloaded) != compute_sha256(local_path):
                raise RuntimeError(f"Uploaded backup checksum verification failed for s3://{self.bucket}/{key}")
        finally:
            downloaded.unlink(missing_ok=True)


class DatabaseBackup:
    """Create encrypted PostgreSQL backups with checksum manifests."""

    def __init__(
        self,
        backup_dir: Path | str | None = None,
        database_url: str | None = None,
        object_store: ObjectStore | None = None,
    ):
        self.backup_dir = Path(backup_dir or settings.BACKUP_DIR)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.connection = parse_database_url(database_url or settings.EFFECTIVE_MIGRATION_DATABASE_URL)
        self.object_store = object_store or ObjectStore()

    def _artifact_stem(self) -> str:
        created = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        git_sha = get_git_sha()
        env = (settings.APP_ENV or "unknown").lower()
        return f"{env}-{created}-{git_sha}"

    def _pg_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PGPASSWORD"] = self.connection.password
        if self.connection.sslmode or self.connection.host.endswith("supabase.co"):
            env["PGSSLMODE"] = self.connection.sslmode or "require"
        return env

    def _run_pg_dump(self, dump_path: Path) -> None:
        cmd = [
            "pg_dump",
            "-h",
            self.connection.host,
            "-p",
            str(self.connection.port),
            "-U",
            self.connection.user,
            "-d",
            self.connection.database,
            "-F",
            "c",
            "--no-owner",
            "--no-acl",
            "--file",
            str(dump_path),
        ]
        _run_command(cmd, env=self._pg_env(), timeout=1800)

    def _encrypt_with_age(self, plaintext_path: Path, encrypted_path: Path) -> None:
        recipient = (settings.BACKUP_ENCRYPTION_PUBLIC_KEY or "").strip()
        if not recipient:
            raise RuntimeError("BACKUP_ENCRYPTION_PUBLIC_KEY is required for encrypted backups")
        cmd = [
            "age",
            "--encrypt",
            "--recipient",
            recipient,
            "--output",
            str(encrypted_path),
            str(plaintext_path),
        ]
        _run_command(cmd, timeout=1800)

    def create_backup(self) -> BackupResult:
        stem = self._artifact_stem()
        backup_id = str(uuid.uuid4())
        dump_path = self.backup_dir / f"{stem}.dump"
        encrypted_path = self.backup_dir / f"{stem}.dump.age"
        manifest_path = self.backup_dir / f"{stem}.manifest.json"

        self._run_pg_dump(dump_path)
        checksum_plaintext = compute_sha256(dump_path)

        try:
            self._encrypt_with_age(dump_path, encrypted_path)
        finally:
            dump_path.unlink(missing_ok=True)

        checksum_encrypted = compute_sha256(encrypted_path)
        manifest = BackupManifest(
            backup_id=backup_id,
            environment=settings.APP_ENV,
            git_sha=get_git_sha(),
            artifact_name=encrypted_path.name,
            artifact_type="postgres",
            created_at=datetime.now(UTC).isoformat(),
            size_bytes=encrypted_path.stat().st_size,
            checksum_plaintext=checksum_plaintext,
            checksum_encrypted=checksum_encrypted,
            postgres_version=get_postgres_version(),
            migration_version=get_current_migration_version(),
            encryption="age",
            retention_tier="daily",
        )
        manifest.write_json(manifest_path)
        return BackupResult(artifact_path=encrypted_path, manifest_path=manifest_path, manifest=manifest)

    def upload_backup(self, result: BackupResult) -> BackupResult:
        artifact_key = self.object_store.key_for("postgres", result.manifest.retention_tier, result.artifact_path.name)
        manifest_key = self.object_store.key_for("manifests", result.manifest.retention_tier, result.manifest_path.name)
        self.object_store.upload_and_verify(result.artifact_path, artifact_key, metadata=result.manifest.to_dict())
        self.object_store.upload_and_verify(result.manifest_path, manifest_key, metadata={"backup_id": result.manifest.backup_id})
        return BackupResult(
            artifact_path=result.artifact_path,
            manifest_path=result.manifest_path,
            manifest=result.manifest,
            uploaded=True,
        )

    def cleanup_local_backups(self, retention_days: int = RETENTION_DAYS) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        for path in self.backup_dir.glob("*.dump.age"):
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if modified < cutoff:
                path.unlink(missing_ok=True)
                manifest = path.with_name(path.name.replace(".dump.age", ".manifest.json"))
                manifest.unlink(missing_ok=True)

    async def run(self) -> bool:
        try:
            result = self.create_backup()
            uploaded = False
            if self.object_store.enabled():
                result = self.upload_backup(result)
                uploaded = result.uploaded
            elif settings.APP_ENV.lower() == "production":
                raise RuntimeError("Production backups require BACKUP_BUCKET and verified off-host upload")

            self.cleanup_local_backups()
            await self._send_notification(
                "Database backup completed\n"
                f"artifact={result.artifact_path.name}\n"
                f"size_bytes={result.manifest.size_bytes}\n"
                f"uploaded={uploaded}"
            )
            return True
        except Exception as exc:
            logger.exception("Database backup failed")
            await self._send_notification(f"Database backup failed: {exc}")
            return False

    async def _send_notification(self, message: str) -> None:
        try:
            from app.telegram_bot.bot import send_message

            await send_message(message, parse_mode=None)
        except Exception as exc:
            logger.warning("Backup notification failed: %s", exc)


class RedisSnapshotBackup:
    """Back up Redis snapshot files alongside PostgreSQL manifests."""

    def __init__(self, backup_dir: Path | str | None = None, object_store: ObjectStore | None = None):
        self.backup_dir = Path(backup_dir or settings.BACKUP_DIR)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.object_store = object_store or ObjectStore()

    def create_backup(self, snapshot_path: Path | str | None = None) -> BackupResult:
        source = Path(snapshot_path or settings.REDIS_SNAPSHOT_PATH)
        if not source.exists():
            raise RuntimeError(f"Redis snapshot does not exist: {source}")

        stem = f"{(settings.APP_ENV or 'unknown').lower()}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{get_git_sha()}"
        copied = self.backup_dir / f"{stem}.redis.rdb"
        encrypted = self.backup_dir / f"{stem}.redis.rdb.age"
        manifest_path = self.backup_dir / f"{stem}.redis.manifest.json"
        shutil.copy2(source, copied)
        checksum_plaintext = compute_sha256(copied)

        recipient = (settings.BACKUP_ENCRYPTION_PUBLIC_KEY or "").strip()
        if not recipient:
            copied.unlink(missing_ok=True)
            raise RuntimeError("BACKUP_ENCRYPTION_PUBLIC_KEY is required for encrypted Redis backups")
        _run_command(
            [
                "age",
                "--encrypt",
                "--recipient",
                recipient,
                "--output",
                str(encrypted),
                str(copied),
            ],
            timeout=1800,
        )
        copied.unlink(missing_ok=True)
        manifest = BackupManifest(
            backup_id=str(uuid.uuid4()),
            environment=settings.APP_ENV,
            git_sha=get_git_sha(),
            artifact_name=encrypted.name,
            artifact_type="redis",
            created_at=datetime.now(UTC).isoformat(),
            size_bytes=encrypted.stat().st_size,
            checksum_plaintext=checksum_plaintext,
            checksum_encrypted=compute_sha256(encrypted),
            postgres_version="n/a",
            migration_version="n/a",
            encryption="age",
            retention_tier="daily",
        )
        manifest.write_json(manifest_path)
        return BackupResult(artifact_path=encrypted, manifest_path=manifest_path, manifest=manifest)

    def upload_backup(self, result: BackupResult) -> BackupResult:
        artifact_key = self.object_store.key_for("redis", result.manifest.retention_tier, result.artifact_path.name)
        manifest_key = self.object_store.key_for("manifests", result.manifest.retention_tier, result.manifest_path.name)
        self.object_store.upload_and_verify(result.artifact_path, artifact_key, metadata=result.manifest.to_dict())
        self.object_store.upload_and_verify(result.manifest_path, manifest_key, metadata={"backup_id": result.manifest.backup_id})
        return BackupResult(result.artifact_path, result.manifest_path, result.manifest, uploaded=True)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create encrypted PostgreSQL backups")
    parser.add_argument("--local-only", action="store_true", help="Skip object-store upload even if configured")
    args = parser.parse_args()

    backup = DatabaseBackup(object_store=ObjectStore(bucket="" if args.local_only else None))
    success = await backup.run()
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
