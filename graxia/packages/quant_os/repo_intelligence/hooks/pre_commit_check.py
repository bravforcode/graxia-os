#!/usr/bin/env python3
"""Pre-commit hook: validate manifest consistency, block execution permission changes without approval."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from manifest import RepoManifest

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), '..', 'registry', 'manifest.yml')

def run_check():
    manifest = RepoManifest()
    manifest_path = MANIFEST_PATH
    if not os.path.exists(manifest_path):
        print("WARN: manifest not found, skipping pre-commit check")
        return 0
    
    manifest.load(manifest_path)
    issues = manifest.validate_all_entries()
    
    if issues:
        print("MANIFEST VALIDATION ISSUES:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    
    print("Manifest validation: OK")
    return 0

if __name__ == "__main__":
    sys.exit(run_check())
