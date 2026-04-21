"""Backup, Redis snapshot, and restore-drill task wrappers."""
from __future__ import annotations

import os
import secrets
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from app.config import settings
from app.core.monitoring import metrics_collector
from app.tasks.base import execute_managed_async_task, idempotent_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import BACKGROUND_QUEUE, CRITICAL_QUEUE, get_sync_redis_client


async def run_daily_backup_async() -> dict[str, str]:
    from scripts.backup_database import DatabaseBackup

    backup = DatabaseBackup()
    success = await backup.run()
    if not success:
        raise RuntimeError("Database backup failed")
    metrics_collector.set_backup_last_success(time.time())
    return {"status": "completed", "type": "postgres"}


async def run_redis_backup_async() -> dict[str, str]:
    from scripts.backup_database import RedisSnapshotBackup

    redis_client = get_sync_redis_client()
    if redis_client is None:
        raise RuntimeError("Redis is not available for BGSAVE")
    redis_client.bgsave()

    started = time.time()
    while time.time() - started < 120:
        try:
            if redis_client.info("persistence").get("rdb_bgsave_in_progress") == 0:
                break
        except Exception:
            break
        time.sleep(2)

    backup = RedisSnapshotBackup()
    result = backup.create_backup()
    if backup.object_store.enabled():
        result = backup.upload_backup(result)
    metrics_collector.set_backup_last_success(time.time())
    return {
        "status": "completed",
        "type": "redis",
        "artifact": result.artifact_path.name,
        "uploaded": str(result.uploaded).lower(),
    }


async def run_restore_drill_async() -> dict[str, str]:
    """Restore the newest local encrypted Postgres backup into a disposable container."""
    from scripts.backup_database import BackupManifest
    from scripts.restore_database import DatabaseRestore

    backup_dir = Path(settings.BACKUP_DIR)
    manifests = sorted(backup_dir.glob("*.manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    selected_manifest: BackupManifest | None = None
    manifest_path: Path | None = None
    artifact_path: Path | None = None
    for candidate in manifests:
        manifest = BackupManifest.from_json(candidate)
        if manifest.artifact_type != "postgres":
            continue
        artifact = backup_dir / manifest.artifact_name
        if artifact.exists():
            selected_manifest = manifest
            manifest_path = candidate
            artifact_path = artifact
            break
    if selected_manifest is None or artifact_path is None or manifest_path is None:
        return {"status": "skipped", "reason": "no_postgres_backup_found"}

    try:
        probe = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if probe.returncode != 0:
            return {"status": "skipped", "reason": "docker_daemon_unavailable"}
    except Exception:
        return {"status": "skipped", "reason": "docker_daemon_unavailable"}

    drill_id = uuid.uuid4().hex[:12]
    container_name = f"restore-drill-{drill_id}"
    db_name = "restore_drill"
    db_password = secrets.token_urlsafe(24)
    work_dir = Path(tempfile.mkdtemp(prefix="restore-drill-"))
    started = time.time()

    def run(cmd: list[str], *, timeout: int = 120, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        if result.returncode != 0:
            raise RuntimeError(f"{cmd[0]} failed: {result.stderr.strip() or result.stdout.strip()}")
        return result

    try:
        run(
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                container_name,
                "-e",
                f"POSTGRES_PASSWORD={db_password}",
                "-e",
                f"POSTGRES_DB={db_name}",
                "-p",
                "127.0.0.1::5432",
                settings.RESTORE_DRILL_POSTGRES_IMAGE,
            ],
            timeout=120,
        )

        port_output = ""
        deadline = time.time() + 90
        while time.time() < deadline:
            port_output = run(["docker", "port", container_name, "5432/tcp"], timeout=20).stdout.strip()
            if port_output:
                host_port = port_output.rsplit(":", 1)[-1]
                probe_env = os.environ.copy()
                probe_env["PGPASSWORD"] = db_password
                probe = subprocess.run(
                    [
                        "pg_isready",
                        "-h",
                        "127.0.0.1",
                        "-p",
                        host_port,
                        "-U",
                        "postgres",
                        "-d",
                        db_name,
                    ],
                    env=probe_env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if probe.returncode == 0:
                    break
            time.sleep(2)
        else:
            raise RuntimeError("Restore drill Postgres container did not become ready")

        host_port = port_output.rsplit(":", 1)[-1]
        target_db = f"postgresql://postgres:{quote(db_password)}@127.0.0.1:{host_port}/{db_name}"
        restore = DatabaseRestore(database_url=target_db)
        dump_path = restore.restore_backup(artifact_path, selected_manifest, work_dir=work_dir)

        env = os.environ.copy()
        env["DATABASE_URL"] = target_db
        run(["alembic", "upgrade", "head"], timeout=600, env=env)

        import psycopg2

        with psycopg2.connect(target_db) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()

        duration = time.time() - started
        metrics_collector.set_restore_drill_last_success(time.time())
        return {
            "status": "completed",
            "backup_id": selected_manifest.backup_id,
            "manifest": str(manifest_path),
            "dump": str(dump_path),
            "duration_seconds": f"{duration:.2f}",
        }
    finally:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, text=True, timeout=60)


@celery_app.task(name="tasks.backup.run_daily_backup", queue=CRITICAL_QUEUE)
@idempotent_task("{task_name}:{date}", lock_ttl=7200)
def daily_backup_task():
    return execute_managed_async_task(
        task_name="daily_backup",
        queue=CRITICAL_QUEUE,
        coroutine_factory=run_daily_backup_async,
    )


@celery_app.task(name="tasks.backup.run_restore_drill", queue=CRITICAL_QUEUE)
@idempotent_task("{task_name}:{date}", lock_ttl=7200)
def restore_drill_task():
    return execute_managed_async_task(
        task_name="restore_drill",
        queue=CRITICAL_QUEUE,
        coroutine_factory=run_restore_drill_async,
    )


@celery_app.task(name="tasks.backup.run_redis_backup", queue=BACKGROUND_QUEUE)
@idempotent_task("{task_name}:{date}", lock_ttl=7200)
def redis_backup_task():
    return execute_managed_async_task(
        task_name="redis_backup",
        queue=BACKGROUND_QUEUE,
        coroutine_factory=run_redis_backup_async,
    )
