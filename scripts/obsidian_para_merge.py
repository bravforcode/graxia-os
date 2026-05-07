#!/usr/bin/env python3
"""
PARA Folder Consolidation Script for Graxia OS
Moves files from legacy unnumbered folders to canonical numbered PARA folders.

Usage:
    python scripts/obsidian_para_merge.py --dry-run     # Preview only
    python scripts/obsidian_para_merge.py --execute   # Actually move
"""
import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

VAULT_ROOT = Path("C:/Users/menum/OneDrive/Documents/Gracia/Second Brain")

MERGE_MAP = {
    "Inbox": "00-Inbox",
    "Projects": "01-Projects",
    "Areas": "02-Areas",
    "Archives": "04-Archive",
    "Templates": "03-Resources/Templates",
}


def merge_folders(dry_run: bool = True):
    conflicts = []
    moves = []
    created_dirs = []

    for src_name, tgt_name in MERGE_MAP.items():
        src = VAULT_ROOT / src_name
        tgt = VAULT_ROOT / tgt_name

        if not src.exists():
            print(f"  SKIP: {src_name}/ does not exist")
            continue

        # Create target if missing
        if not tgt.exists():
            if not dry_run:
                tgt.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(tgt_name))

        # Move files
        for item in src.iterdir():
            dest = tgt / item.name

            if dest.exists():
                # Name conflict — append _merged suffix
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                new_name = f"{item.stem}_merged_{timestamp}{item.suffix}"
                dest = dest.with_name(new_name)
                conflicts.append((str(item.relative_to(VAULT_ROOT)), str(dest.relative_to(VAULT_ROOT))))

            moves.append((item, dest))
            if not dry_run:
                if item.is_dir():
                    shutil.move(str(item), str(dest))
                else:
                    shutil.move(str(item), str(dest))

        # Delete source if empty after move
        if not dry_run:
            remaining = list(src.iterdir())
            if not remaining:
                shutil.rmtree(src)
                print(f"  DELETED empty: {src_name}/")
            else:
                print(f"  WARN: {src_name}/ still has {len(remaining)} items — not deleted")

    print(f"\n{'='*60}")
    print(f"{'DRY RUN — ' if dry_run else ''}Summary")
    print(f"{'='*60}")
    print(f"  Folders to process: {len(MERGE_MAP)}")
    print(f"  Items to move: {len(moves)}")
    print(f"  Conflicts resolved: {len(conflicts)}")
    print(f"  Directories created: {len(created_dirs)}")
    if conflicts:
        print("\n  Conflicts (renamed with _merged suffix):")
        for c in conflicts:
            print(f"    {c[0]} -> {c[1]}")
    if created_dirs:
        print("\n  Directories created:")
        for d in created_dirs:
            print(f"    {d}/")
    print(f"\n  Items to move:")
    for m in moves:
        rel_src = m[0].relative_to(VAULT_ROOT)
        rel_dst = m[1].relative_to(VAULT_ROOT)
        print(f"    {rel_src} -> {rel_dst}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Consolidate Obsidian PARA folders")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Preview moves without executing")
    parser.add_argument("--execute", action="store_true", help="Actually move files")
    args = parser.parse_args()

    if not VAULT_ROOT.exists():
        print(f"ERROR: Vault root not found: {VAULT_ROOT}")
        sys.exit(1)

    dry_run = not args.execute
    merge_folders(dry_run=dry_run)
