"""Verify repository cleanup prerequisites without archiving or deleting anything.

The guard checks the declared inventory, protects explicitly protected repos,
and verifies an existing local Git bundle. It performs no GitHub or filesystem
cleanup mutation.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts.repository_inventory import (
        PROTECTED_REPOSITORIES,
        InventoryError,
        load_inventory,
    )
except ModuleNotFoundError:  # Supports `python scripts/repository_bundle_guard.py`.
    from repository_inventory import (  # type: ignore[no-redef]
        PROTECTED_REPOSITORIES,
        InventoryError,
        load_inventory,
    )


class BundleGuardError(ValueError):
    """Raised when cleanup evidence is unsafe or incomplete."""


_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_BUNDLE_REQUIRED_ACTIONS = {
    "merge-then-archive",
    "archive",
    "quarantine-then-delete",
    "already-archived",
}


def _run_git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BundleGuardError("git bundle verification failed") from exc
    return result.stdout


def _inventory_entry(inventory: Mapping[str, Any], repo_name: str) -> Mapping[str, Any]:
    for item in inventory["repositories"]:
        if item["name"] == repo_name:
            return item
    raise BundleGuardError(f"repository is absent from audited inventory: {repo_name}")


def validate_cleanup_target(
    inventory: Mapping[str, Any],
    *,
    repo_name: str,
    action: str,
    bundle_path: str | Path,
) -> Mapping[str, Any]:
    """Validate a cleanup target before any external write is considered."""
    entry = _inventory_entry(inventory, repo_name)
    if repo_name in PROTECTED_REPOSITORIES or entry.get("protected") is True:
        if action != "keep-active":
            raise BundleGuardError(f"protected repository cannot be cleaned: {repo_name}")
    if entry.get("action") != action:
        raise BundleGuardError(
            f"action does not match inventory for {repo_name}: {action}"
        )
    target = Path(bundle_path).expanduser().resolve()
    if action in _BUNDLE_REQUIRED_ACTIONS:
        if not target.is_file():
            raise BundleGuardError(f"restore bundle is missing: {target}")
    return entry


def _parse_heads(output: str) -> list[str]:
    heads: list[str] = []
    for line in output.splitlines():
        value = line.strip().split(maxsplit=1)
        if value and _HEX40.fullmatch(value[0]):
            heads.append(value[0])
    return heads


def verify_bundle(
    inventory: Mapping[str, Any],
    *,
    repo_name: str,
    action: str,
    bundle_path: str | Path,
    expected_head: str | None = None,
) -> dict[str, Any]:
    validate_cleanup_target(
        inventory,
        repo_name=repo_name,
        action=action,
        bundle_path=bundle_path,
    )
    if expected_head is not None and not _HEX40.fullmatch(expected_head):
        raise BundleGuardError("expected head must be a 40-character lowercase SHA")
    bundle = str(Path(bundle_path).expanduser().resolve())
    _run_git("bundle", "verify", bundle)
    heads = _parse_heads(_run_git("bundle", "list-heads", bundle))
    if not heads:
        raise BundleGuardError("verified bundle contains no safe heads")
    if expected_head is not None and expected_head not in heads:
        raise BundleGuardError("verified bundle does not contain expected head")
    return {
        "repository": repo_name,
        "declared_action": action,
        "bundle_path": bundle,
        "verified": True,
        "head_count": len(heads),
        "expected_head": expected_head,
        "expected_head_present": expected_head is None or expected_head in heads,
        "external_writes": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", default="docs/repository-inventory.yaml")
    parser.add_argument("--repo-name", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--expected-head")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        inventory = load_inventory(args.inventory)
        report = verify_bundle(
            inventory,
            repo_name=args.repo_name,
            action=args.action,
            bundle_path=args.bundle,
            expected_head=args.expected_head,
        )
        payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload, encoding="utf-8")
        print(json.dumps({"status": "ok", **report}, sort_keys=True))
        return 0
    except (BundleGuardError, InventoryError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
