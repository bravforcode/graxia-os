"""Settings each scheduled task needs before it can do useful work.

Keys are the managed ``task_name`` passed to ``execute_managed_async_task``.
"""
from __future__ import annotations

from app.config import settings

_GOOGLE_WORKSPACE = (
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REFRESH_TOKEN",
    "GOOGLE_WORKSPACE_EMAIL",
)

TASK_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    # Gmail fetch needs Google Workspace OAuth credentials (HAS_REAL_GOOGLE_WORKSPACE_CREDENTIALS).
    "email_processing": _GOOGLE_WORKSPACE,
    # Postgres backups are age-encrypted; DatabaseBackup raises without a recipient key.
    "daily_backup": ("BACKUP_ENCRYPTION_PUBLIC_KEY",),
    # Redis snapshots are age-encrypted; RedisSnapshotBackup raises without a recipient key.
    "redis_backup": ("BACKUP_ENCRYPTION_PUBLIC_KEY",),
}


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    get_secret = getattr(value, "get_secret_value", None)
    if callable(get_secret):
        value = get_secret()
    return not str(value or "").strip()


def missing_settings(task_name: str) -> list[str]:
    return [key for key in TASK_REQUIREMENTS.get(task_name, ()) if _is_blank(getattr(settings, key, ""))]
