"""
Log rotation and cleanup.

Rotates JSONL log files by size (10 MB default) or time (daily).
Compresses rotated files with gzip and retains for 30 days.
"""

from __future__ import annotations

import gzip
import shutil
from datetime import datetime, timedelta, UTC
from pathlib import Path


DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_RETENTION_DAYS = 30


def rotate_by_size(
    path: Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = 5,
) -> bool:
    """Rotate file if it exceeds max_bytes. Returns True if rotated."""
    if not path.exists() or path.stat().st_size <= max_bytes:
        return False

    for i in range(backup_count - 1, 0, -1):
        src = path.with_suffix(path.suffix + f".{i}")
        dst = path.with_suffix(path.suffix + f".{i + 1}")
        if src.exists():
            if dst.exists():
                dst.unlink()
            src.rename(dst)

    backup = path.with_suffix(path.suffix + ".1")
    if backup.exists():
        backup.unlink()
    path.rename(backup)
    return True


def rotate_by_time(
    path: Path,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> bool:
    """
    Rotate file if its last modification is from a previous day.
    Appends date stamp and compresses.
    Returns True if rotated.
    """
    if not path.exists():
        return False

    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    now = datetime.now(UTC)

    if mtime.date() >= now.date():
        return False

    date_stamp = mtime.strftime("%Y%m%d")
    rotated_name = path.with_name(f"{path.stem}.{date_stamp}{path.suffix}")
    if rotated_name.exists():
        rotated_name.unlink()
    path.rename(rotated_name)
    _gzip_file(rotated_name)
    _cleanup_old(rotated_name.parent, path.stem, path.suffix, retention_days)
    return True


def _gzip_file(path: Path) -> Path:
    """Compress file with gzip, remove original."""
    gz_path = path.with_suffix(path.suffix + ".gz")
    with open(path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    path.unlink()
    return gz_path


def _cleanup_old(
    directory: Path,
    stem: str,
    suffix: str,
    retention_days: int,
) -> int:
    """Remove compressed logs older than retention_days. Returns count removed."""
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    removed = 0
    for gz_file in directory.glob(f"{stem}.????????" + suffix + ".gz"):
        try:
            date_str = gz_file.stem.split(".")[-2]
            file_date = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=UTC)
            if file_date < cutoff:
                gz_file.unlink()
                removed += 1
        except (ValueError, IndexError):
            pass
    return removed


def rotate_all(
    log_dir: str | Path = "logs",
    max_bytes: int = DEFAULT_MAX_BYTES,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> dict[str, bool]:
    """Rotate all JSONL files in log_dir by size, then time-based."""
    directory = Path(log_dir)
    if not directory.exists():
        return {}

    results: dict[str, bool] = {}
    for log_file in sorted(directory.glob("*.jsonl")):
        rotated = rotate_by_size(log_file, max_bytes)
        if not rotated:
            rotated = rotate_by_time(log_file, retention_days)
        results[str(log_file.name)] = rotated
    return results
