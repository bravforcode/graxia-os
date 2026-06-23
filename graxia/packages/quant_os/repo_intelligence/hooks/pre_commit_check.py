#!/usr/bin/env python3
"""Pre-commit hook: validate the canonical repository registry fail-closed."""
import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hooks.registry_check import REQUIRED_FIELDS, _extract_entries

REGISTRY_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "registry",
    "repositories_canonical.yml",
)


def run_check(registry_path: str = REGISTRY_PATH) -> int:
    if not os.path.exists(registry_path):
        print(f"ERROR: required canonical registry not found: {registry_path}")
        return 1

    try:
        with open(registry_path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except Exception as exc:
        print(f"ERROR: failed to load canonical registry {registry_path}: {exc}")
        return 1

    if data is None:
        print(f"ERROR: canonical registry is empty: {registry_path}")
        return 1

    try:
        entries = _extract_entries(data)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    if not entries:
        print(f"ERROR: canonical registry contains no entries: {registry_path}")
        return 1

    issues: list[str] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            issues.append(f"Entry {index}: invalid type {type(entry).__name__}")
            continue
        entry_name = entry.get("repo_id", entry.get("name", f"#{index}"))
        for field in REQUIRED_FIELDS:
            if field not in entry:
                issues.append(f"Entry {entry_name}: missing {field}")

    if issues:
        print("CANONICAL REGISTRY VALIDATION ISSUES:")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print(f"Canonical registry validation: OK ({len(entries)} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(run_check())
