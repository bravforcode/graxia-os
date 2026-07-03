"""
State Restore — restore trading state files from a backup.

Usage:
    python scripts/restore_state.py                     # list available backups
    python scripts/restore_state.py --latest            # restore from latest backup
    python scripts/restore_state.py --date 2026-07-03   # restore from specific date
    python scripts/restore_state.py --dir 2026-07-03_120000  # restore from specific dir
    python scripts/restore_state.py --validate          # validate backup integrity
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("restore_state")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def list_backups() -> list[dict]:
    """List all available backups, newest first."""
    if not BACKUP_ROOT.exists():
        return []

    backups = []
    for entry in BACKUP_ROOT.iterdir():
        if not entry.is_dir():
            continue
        try:
            dir_time = datetime.strptime(entry.name, "%Y-%m-%d_%H%M%S")
        except ValueError:
            continue

        manifest_path = entry / "manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Calculate total size
        total_size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())

        backups.append(
            {
                "dir_name": entry.name,
                "timestamp": dir_time.isoformat(),
                "files_backed_up": manifest.get("files_backed_up", 0),
                "total_size_bytes": total_size,
                "errors": manifest.get("errors", []),
                "path": str(entry),
            }
        )

    backups.sort(key=lambda b: b["dir_name"], reverse=True)
    return backups


def find_backup(target: str) -> Path | None:
    """Find a backup directory by date prefix or exact name."""
    if not BACKUP_ROOT.exists():
        return None

    # Try exact match first
    exact = BACKUP_ROOT / target
    if exact.is_dir():
        return exact

    # Try date prefix match (YYYY-MM-DD)
    matches = []
    for entry in BACKUP_ROOT.iterdir():
        if entry.is_dir() and entry.name.startswith(target):
            matches.append(entry)

    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        # Return newest match
        matches.sort(key=lambda p: p.name, reverse=True)
        logger.warning("Multiple matches for '%s', using newest: %s", target, matches[0].name)
        return matches[0]

    return None


def validate_backup(backup_dir: Path) -> dict:
    """Validate backup integrity by checking manifest and files."""
    result = {"valid": True, "issues": []}

    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        result["valid"] = False
        result["issues"].append("Missing manifest.json")
        return result

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        result["valid"] = False
        result["issues"].append(f"Corrupt manifest.json: {e}")
        return result

    # Check each file in manifest exists
    for rel_path in manifest.get("state_files_found", []):
        backed_file = backup_dir / rel_path
        if not backed_file.exists():
            result["valid"] = False
            result["issues"].append(f"Missing backed-up file: {rel_path}")
        elif backed_file.stat().st_size == 0:
            result["issues"].append(f"Empty backed-up file: {rel_path}")

    # Verify JSON state files are valid (only check files we tracked, not all data/ files)
    for rel_path in manifest.get("state_files_found", []):
        if not rel_path.endswith(".json"):
            continue
        backed_file = backup_dir / rel_path
        if not backed_file.exists():
            continue
        try:
            json.loads(backed_file.read_text(encoding="utf-8"))
        except Exception as e:
            result["valid"] = False
            result["issues"].append(f"Corrupt JSON: {rel_path}: {e}")

    return result


def restore_from_backup(backup_dir: Path, dry_run: bool = False) -> dict:
    """Restore state files from a backup directory."""
    logger.info("Restoring from: %s", backup_dir.name)

    # Validate first
    validation = validate_backup(backup_dir)
    if not validation["valid"]:
        logger.error("Backup validation failed: %s", validation["issues"])
        return {"status": "validation_failed", "issues": validation["issues"]}

    if validation["issues"]:
        for issue in validation["issues"]:
            logger.warning("  Warning: %s", issue)

    # Restore individual state files
    restored = 0
    errors = []

    # Restore from data/ subdirectory in backup
    data_backup = backup_dir / "data"
    if data_backup.exists():
        data_dest = PROJECT_ROOT / "data"
        if dry_run:
            for f in data_backup.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(data_backup)
                    logger.info("  [DRY RUN] Would restore: data/%s", rel)
        else:
            data_dest.mkdir(parents=True, exist_ok=True)
            for f in data_backup.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(data_backup)
                    dest = data_dest / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(str(f), str(dest))
                        logger.info("  Restored: data/%s", rel)
                        restored += 1
                    except Exception as e:
                        logger.error("  Failed to restore data/%s: %s", rel, e)
                        errors.append(f"data/{rel}")

    # Restore state/ subdirectory in backup
    state_backup = backup_dir / "state"
    if state_backup.exists():
        state_dest = PROJECT_ROOT / "state"
        if dry_run:
            for f in state_backup.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(state_backup)
                    logger.info("  [DRY RUN] Would restore: state/%s", rel)
        else:
            state_dest.mkdir(parents=True, exist_ok=True)
            for f in state_backup.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(state_backup)
                    dest = state_dest / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(str(f), str(dest))
                        logger.info("  Restored: state/%s", rel)
                        restored += 1
                    except Exception as e:
                        logger.error("  Failed to restore state/%s: %s", rel, e)
                        errors.append(f"state/{rel}")

    # Also restore any top-level state files in backup root
    for src in backup_dir.iterdir():
        if src.is_file() and src.name != "manifest.json":
            dest = PROJECT_ROOT / src.name
            if dry_run:
                logger.info("  [DRY RUN] Would restore: %s", src.name)
            else:
                try:
                    shutil.copy2(str(src), str(dest))
                    logger.info("  Restored: %s", src.name)
                    restored += 1
                except Exception as e:
                    logger.error("  Failed to restore %s: %s", src.name, e)
                    errors.append(src.name)

    status = "success" if not errors else "partial"
    logger.info("=== Restore complete: %s (%d files) ===", status, restored)
    return {"status": status, "restored": restored, "errors": errors}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    args = sys.argv[1:]

    if not args or "--list" in args:
        backups = list_backups()
        if not backups:
            print("No backups found.")
            return
        print(f"\nAvailable backups ({len(backups)}):\n")
        for b in backups:
            errors_str = f" ERRORS: {b['errors']}" if b["errors"] else ""
            print(f"  {b['dir_name']}  ({b['files_backed_up']} files, {b['total_size_bytes']:,} bytes){errors_str}")
        print()
        return

    if "--validate" in args:
        target = None
        for a in args:
            if a not in ("--validate", "--latest"):
                target = a
        if not target:
            backups = list_backups()
            if not backups:
                print("No backups to validate.")
                return
            target = backups[0]["dir_name"]

        backup_dir = find_backup(target)
        if not backup_dir:
            print(f"Backup not found: {target}")
            sys.exit(1)

        result = validate_backup(backup_dir)
        print(f"\nValidation of {backup_dir.name}:")
        print(f"  Valid: {result['valid']}")
        if result["issues"]:
            for issue in result["issues"]:
                print(f"  Issue: {issue}")
        sys.exit(0 if result["valid"] else 1)

    if "--latest" in args:
        backups = list_backups()
        if not backups:
            print("No backups found.")
            sys.exit(1)
        backup_dir = find_backup(backups[0]["dir_name"])
    else:
        # Find by date or dir name
        target = [a for a in args if not a.startswith("--")][0]
        backup_dir = find_backup(target)
        if not backup_dir:
            print(f"Backup not found: {target}")
            sys.exit(1)

    dry_run = "--dry-run" in args
    result = restore_from_backup(backup_dir, dry_run=dry_run)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
