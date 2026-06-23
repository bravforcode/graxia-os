#!/usr/bin/env python3
"""Pre-commit hook: validate manifest policy and canonical registry consistency fail-closed."""
import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hooks.registry_check import REQUIRED_FIELDS, _extract_entries
from manifest import RepoManifest

REGISTRY_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "registry",
    "repositories_canonical.yml",
)
MANIFEST_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "registry",
    "manifest.yml",
)

ROLE_TO_TIER = {
    "APPROVED_DIFFERENTIAL_ORACLE": "A",
    "APPROVED_ARCHITECTURE_REFERENCE": "B",
    "APPROVED_HYPOTHESIS_CORPUS": "C",
    "VERIFY_IDENTITY_ONLY": "C",
    "CRYPTO_ONLY_REFERENCE": "C",
    "APPROVED_DATA_REFERENCE": "D",
    "QUARANTINED": "Q",
}

ROLE_TO_RUNTIME_BOUNDARY = {
    "APPROVED_DIFFERENTIAL_ORACLE": "isolated_research_container",
    "APPROVED_ARCHITECTURE_REFERENCE": "read_only_reference",
    "APPROVED_HYPOTHESIS_CORPUS": "hypothesis_only",
    "VERIFY_IDENTITY_ONLY": "read_only_reference",
    "CRYPTO_ONLY_REFERENCE": "read_only_reference",
    "APPROVED_DATA_REFERENCE": "data_reference",
    "QUARANTINED": "quarantine",
}


def _load_registry_entries(registry_path: str) -> tuple[list[dict], list[str]]:
    if not os.path.exists(registry_path):
        return [], [f"required canonical registry not found: {registry_path}"]

    try:
        with open(registry_path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except Exception as exc:
        return [], [f"failed to load canonical registry {registry_path}: {exc}"]

    if data is None:
        return [], [f"canonical registry is empty: {registry_path}"]

    try:
        entries = _extract_entries(data)
    except ValueError as exc:
        return [], [str(exc)]

    if not entries:
        return [], [f"canonical registry contains no entries: {registry_path}"]

    issues: list[str] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            issues.append(f"Entry {index}: invalid type {type(entry).__name__}")
            continue
        entry_name = entry.get("repo_id", entry.get("name", f"#{index}"))
        for field in REQUIRED_FIELDS:
            if field not in entry:
                issues.append(f"Entry {entry_name}: missing {field}")
    return entries, issues


def _expected_manifest_entry(entry: dict) -> dict:
    role = entry["allowed_role"]
    tier = ROLE_TO_TIER.get(role)
    runtime_boundary = ROLE_TO_RUNTIME_BOUNDARY.get(role)
    if tier is None or runtime_boundary is None:
        raise ValueError(f"unsupported allowed_role in canonical registry: {role}")

    name = entry.get("repo_id") or entry.get("name")
    if not name:
        raise ValueError("registry entry missing repo_id/name")

    review_verdict = "QUARANTINED" if entry["quarantine_status"] else "APPROVED"
    execution_allowed = tier == "A" and bool(entry["execution_permission"])
    return {
        "name": name,
        "tier": tier,
        "role": role,
        "asset_class": entry["asset_scope"],
        "runtime_boundary": runtime_boundary,
        "permissions": {
            "execution": execution_allowed,
            "network": bool(entry["network_permission"]),
            "secrets": bool(entry["credential_permission"]),
            "production_import": False,
        },
        "canonical_url": entry["canonical_url"],
        "pinned_commit": entry["pinned_commit"],
        "license": entry["license_spdx"],
        "review_verdict": review_verdict,
        "sbom_status": "NOT_GENERATED",
        "security_scan": "NOT_SCANNED",
    }


def _load_manifest(manifest_path: str) -> tuple[RepoManifest | None, list[str]]:
    manifest = RepoManifest()
    if not os.path.exists(manifest_path):
        return None, [f"required manifest not found: {manifest_path}"]

    try:
        manifest.load(manifest_path)
    except Exception as exc:
        return None, [f"failed to load manifest {manifest_path}: {exc}"]

    if not manifest.list_entries():
        return None, [f"manifest has no entries: {manifest_path}"]

    return manifest, manifest.validate_all_entries()


def _compare_manifest_to_registry(manifest: RepoManifest, entries: list[dict]) -> list[str]:
    issues: list[str] = []
    expected_names: set[str] = set()

    for entry in entries:
        try:
            expected = _expected_manifest_entry(entry)
        except ValueError as exc:
            issues.append(str(exc))
            continue

        expected_name = expected["name"]
        expected_names.add(expected_name)
        actual = manifest.get_entry(expected_name)
        if actual is None:
            issues.append(f"{expected_name}: missing from manifest")
            continue
        if actual.to_dict() != expected:
            issues.append(f"{expected_name}: manifest entry does not match canonical registry")

    actual_names = {item.name for item in manifest.list_entries()}
    extra_names = sorted(actual_names - expected_names)
    for extra_name in extra_names:
        issues.append(f"{extra_name}: present in manifest but absent from canonical registry")

    if len(actual_names) != len(expected_names):
        issues.append(
            "manifest entry count mismatch: "
            f"manifest={len(actual_names)} canonical={len(expected_names)}"
        )

    return issues


def run_check(
    registry_path: str = REGISTRY_PATH,
    manifest_path: str = MANIFEST_PATH,
) -> int:
    entries, registry_issues = _load_registry_entries(registry_path)
    if registry_issues:
        print("CANONICAL REGISTRY VALIDATION ISSUES:")
        for issue in registry_issues:
            print(f"  - {issue}")
        return 1

    manifest, manifest_issues = _load_manifest(manifest_path)
    if manifest_issues:
        print("MANIFEST VALIDATION ISSUES:")
        for issue in manifest_issues:
            print(f"  - {issue}")
        return 1

    assert manifest is not None
    consistency_issues = _compare_manifest_to_registry(manifest, entries)
    if consistency_issues:
        print("MANIFEST CONSISTENCY ISSUES:")
        for issue in consistency_issues:
            print(f"  - {issue}")
        return 1

    print(
        "Manifest validation: OK "
        f"({len(manifest.list_entries())} entries, canonical={len(entries)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(run_check())
