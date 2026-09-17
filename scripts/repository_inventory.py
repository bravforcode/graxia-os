"""Validate the read-only repository disposition inventory.

The YAML file intentionally uses JSON syntax, which is valid YAML 1.2.
This keeps the checker dependency-free while remaining easy to consume.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


class InventoryError(ValueError):
    """Raised when cleanup inventory violates safety rules."""


AUDITED_REPOSITORIES = {
    "fastwork-promo-automation",
    "vibescity-live",
    "bravforcode",
    "lotusdis",
    "Safescan-ai",
    "Intersite-Track",
    "gosoft",
    "mu-x-harvard",
    "flashfix-ai",
    "graxia-os",
    "OBS-rag",
    "thaolai-web",
    "adminmate-ai",
    "krisphy",
    "graxia-trade",
    "Train-llm",
    "enterprise-agent-os",
    "thaireview-platform",
    "thailand-flood-monitor",
    "portfolio-production",
    "ai-factory",
    "Solven",
    "harvest-ecc",
    "sriracha-coast-watch",
    "Nasa-hackathon-2026",
    "climate-web",
    "auto-post",
    "jobshield-ai",
    "prompt-perfected",
    "NIGHT_SALVAGE",
    "revenue-os",
}
PROTECTED_REPOSITORIES = {"krisphy", "adminmate-ai"}
ALLOWED_ACTIONS = {
    "keep-active",
    "merge-then-archive",
    "archive",
    "already-archived",
    "quarantine-then-delete",
}


def load_inventory(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InventoryError(f"cannot read inventory: {target}") from exc
    return validate_inventory(value)


def validate_inventory(data: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise InventoryError("inventory must be an object")
    audit = data.get("audit")
    repositories = data.get("repositories")
    if not isinstance(audit, Mapping) or audit.get("external_writes") is not False:
        raise InventoryError("inventory must state external_writes=false")
    if not isinstance(repositories, list):
        raise InventoryError("repositories must be a list")
    names = [
        item.get("name") if isinstance(item, Mapping) else None
        for item in repositories
    ]
    if any(not isinstance(name, str) or not name for name in names):
        raise InventoryError("every repository needs a name")
    if len(names) != len(set(names)):
        raise InventoryError("duplicate repository name")
    if set(names) != AUDITED_REPOSITORIES:
        missing = sorted(AUDITED_REPOSITORIES - set(names))
        extra = sorted(set(names) - AUDITED_REPOSITORIES)
        raise InventoryError(
            f"repository set mismatch; missing={missing}, extra={extra}"
        )
    for item in repositories:
        action = item.get("action")
        if action not in ALLOWED_ACTIONS:
            raise InventoryError(f"invalid action for {item['name']}: {action}")
        if item.get("protected") is True and action != "keep-active":
            raise InventoryError(
                f"protected repository has cleanup action: {item['name']}"
            )
        if item["name"] in PROTECTED_REPOSITORIES:
            if item.get("protected") is not True or action != "keep-active":
                raise InventoryError(
                    f"protected repository has cleanup action: {item['name']}"
                )
    return data if isinstance(data, dict) else dict(data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate repository inventory")
    parser.add_argument(
        "path",
        nargs="?",
        default="docs/repository-inventory.yaml",
        help="JSON-subset YAML inventory path",
    )
    args = parser.parse_args()
    load_inventory(args.path)
    print(f"inventory-ok: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
