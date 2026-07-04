"""
Daily State Backup — backs up all critical trading state files.

Backs up:
  - data/kill_switch_state.json
  - data/circuit_breaker_state.json
  - data/risk_ledger.json
  - data/auto_stop_state.json
  - data/risk_overlay_state.json
  - data/execution_ledger.jsonl
  - state/system_state.json

Keeps last 7 daily backups with date-stamped directory names.
Logs backup status to backups/backup.log.

Usage:
    python scripts/backup_state.py              # run backup
    python scripts/backup_state.py --dry-run    # show what would be backed up
"""

import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKUP_ROOT = PROJECT_ROOT / "backups"
KEEP_DAYS = 7

# All state files that need backing up (relative to PROJECT_ROOT)
STATE_FILES: list[str] = [
    "data/kill_switch_state.json",
    "data/circuit_breaker_state.json",
    "data/risk_ledger.json",
    "data/auto_stop_state.json",
    "data/risk_overlay_state.json",
    "data/execution_ledger.jsonl",
    "state/system_state.json",
]

# Also back up the entire data/ directory if it exists (catches any new files)
BACKUP_DATA_DIR = False  # Only back up specific state files, not market data

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FILE = BACKUP_ROOT / "backup.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("backup_state")


_file_handler_added = False


def _add_file_handler():
    """Add file handler after BACKUP_ROOT is ensured to exist (idempotent)."""
    global _file_handler_added
    if _file_handler_added:
        return
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)
    _file_handler_added = True


# ---------------------------------------------------------------------------
# Core backup logic
# ---------------------------------------------------------------------------


def get_backup_dir_name() -> str:
    """Return date-stamped backup directory name: YYYY-MM-DD_HHMMSS."""
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def collect_state_files() -> list[Path]:
    """Return list of state files that exist on disk."""
    found = []
    for rel in STATE_FILES:
        p = PROJECT_ROOT / rel
        if p.exists():
            found.append(p)
        else:
            logger.debug("State file not found (skipping): %s", rel)
    return found


def rotate_backups(keep_days: int = KEEP_DAYS) -> int:
    """Delete backup directories older than keep_days. Returns count removed."""
    if not BACKUP_ROOT.exists():
        return 0

    cutoff = datetime.now().timestamp() - (keep_days * 86400)
    removed = 0

    for entry in BACKUP_ROOT.iterdir():
        if not entry.is_dir():
            continue
        # Backup dirs are named YYYY-MM-DD_HHMMSS
        try:
            dir_time = datetime.strptime(entry.name, "%Y-%m-%d_%H%M%S")
        except ValueError:
            continue
        if dir_time.timestamp() < cutoff:
            shutil.rmtree(entry)
            logger.info("Rotated old backup: %s", entry.name)
            removed += 1

    return removed


def backup_state(dry_run: bool = False) -> dict:
    """Perform the backup. Returns summary dict."""
    _add_file_handler()

    timestamp = get_backup_dir_name()
    backup_dir = BACKUP_ROOT / timestamp

    logger.info("=== Backup started: %s ===", timestamp)

    # Collect files
    state_files = collect_state_files()
    data_dir = PROJECT_ROOT / "data"

    if not state_files and not (BACKUP_DATA_DIR and data_dir.exists()):
        logger.warning("No state files found to back up")
        return {"status": "empty", "files": 0, "backup_dir": str(backup_dir)}

    logger.info("Found %d state file(s) to back up", len(state_files))

    if dry_run:
        for f in state_files:
            logger.info("  [DRY RUN] Would back up: %s (%d bytes)", f.name, f.stat().st_size)
        if BACKUP_DATA_DIR and data_dir.exists():
            logger.info("  [DRY RUN] Would back up data/ directory")
        return {"status": "dry_run", "files": len(state_files), "backup_dir": str(backup_dir)}

    # Create backup directory
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Back up individual state files
    backed_up = 0
    errors = []
    for src in state_files:
        rel = src.relative_to(PROJECT_ROOT)
        dest = backup_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(str(src), str(dest))
            logger.info("  Backed up: %s (%d bytes)", rel, src.stat().st_size)
            backed_up += 1
        except Exception as e:
            logger.error("  Failed to back up %s: %s", rel, e)
            errors.append(str(rel))

    # Back up entire data/ directory (catches any new files)
    if BACKUP_DATA_DIR and data_dir.exists():
        data_dest = backup_dir / "data"
        try:
            if data_dest.exists():
                shutil.rmtree(str(data_dest))
            shutil.copytree(str(data_dir), str(data_dest))
            logger.info("  Backed up data/ directory")
        except Exception as e:
            logger.error("  Failed to back up data/ directory: %s", e)
            errors.append("data/")

    # Write manifest
    manifest = {
        "timestamp": timestamp,
        "created_at": datetime.now().isoformat(),
        "files_backed_up": backed_up,
        "errors": errors,
        "state_files_found": [str(f.relative_to(PROJECT_ROOT)) for f in state_files],
    }
    manifest_path = backup_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Rotate old backups
    rotated = rotate_backups()
    if rotated:
        logger.info("Rotated %d old backup(s)", rotated)

    # Summary
    status = "success" if not errors else "partial"
    logger.info("=== Backup complete: %s (%d files, %d errors) ===", status, backed_up, len(errors))

    return {
        "status": status,
        "files": backed_up,
        "errors": errors,
        "backup_dir": str(backup_dir),
        "rotated": rotated,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    dry_run = "--dry-run" in sys.argv
    result = backup_state(dry_run=dry_run)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] in ("success", "dry_run", "empty") else 1)


if __name__ == "__main__":
    main()
