#!/usr/bin/env python3
"""Check that registry YAML is valid and entries have required fields."""
import sys
import os
import yaml

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), '..', 'registry', 'repositories_canonical.yml')
REQUIRED_FIELDS = (
    "repo_id",
    "canonical_url",
    "owner",
    "name",
    "asset_scope",
    "language",
    "license_spdx",
    "pinned_commit",
    "observed_at_utc",
    "allowed_role",
    "execution_permission",
    "credential_permission",
    "network_permission",
    "quarantine_status",
)


def _extract_entries(data: object) -> list[dict]:
    if isinstance(data, dict):
        entries = data.get("repositories")
        if entries is None:
            raise ValueError("registry missing 'repositories' list")
    elif isinstance(data, list):
        entries = data
    else:
        raise ValueError("registry must be a list or a mapping with 'repositories'")

    if not isinstance(entries, list):
        raise ValueError("registry entries must be a list")

    return entries


def run_check(registry_path: str = REGISTRY_PATH) -> int:
    if not os.path.exists(registry_path):
        print(f"ERROR: required registry not found: {registry_path}")
        return 1

    try:
        with open(registry_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        print(f"ERROR: failed to load registry {registry_path}: {exc}")
        return 1

    if data is None:
        print(f"ERROR: registry is empty: {registry_path}")
        return 1

    try:
        entries = _extract_entries(data)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    if not entries:
        print(f"ERROR: registry contains no entries: {registry_path}")
        return 1

    issues = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            issues.append(f"Entry {index}: invalid type {type(entry).__name__}")
            continue
        for field in REQUIRED_FIELDS:
            if field not in entry:
                issues.append(f"Entry {entry.get('repo_id', entry.get('name', f'#{index}'))}: missing {field}")

    if issues:
        print("REGISTRY ISSUES:")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print(f"Registry check: OK ({len(entries)} entries)")
    return 0

if __name__ == "__main__":
    sys.exit(run_check())
