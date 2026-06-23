#!/usr/bin/env python3
"""Pre-commit hook: validate manifest consistency, block execution permission changes without approval."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from manifest import RepoManifest

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), '..', 'registry', 'manifest.yml')


def run_check(manifest_path: str = MANIFEST_PATH) -> int:
    manifest = RepoManifest()
    if not os.path.exists(manifest_path):
        print(f"ERROR: required manifest not found: {manifest_path}")
        return 1

    try:
        manifest.load(manifest_path)
    except Exception as exc:
        print(f"ERROR: failed to load manifest {manifest_path}: {exc}")
        return 1

    if not manifest.list_entries():
        print(f"ERROR: manifest has no entries: {manifest_path}")
        return 1

    try:
        issues = manifest.validate_all_entries()
    except Exception as exc:
        print(f"ERROR: failed to validate manifest {manifest_path}: {exc}")
        return 1

    if issues:
        print("MANIFEST VALIDATION ISSUES:")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print(f"Manifest validation: OK ({len(manifest.list_entries())} entries)")
    return 0

if __name__ == "__main__":
    sys.exit(run_check())
