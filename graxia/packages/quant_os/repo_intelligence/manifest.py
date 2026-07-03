import json
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml
import hashlib


class RepoTier(Enum):
    A = "A"  # Independent research oracle — Never execute
    B = "B"  # Architecture/API reference — Never execute
    C = "C"  # Hypothesis/feature corpus — Never execute
    D = "D"  # Data reference — Never execute without source validation
    Q = "Q"  # Quarantine — Never, no secrets, no network execution
    R = "R"  # Rejected — Never


@dataclass
class RepoPermissions:
    execution: bool = False
    network: bool = False
    secrets: bool = False
    production_import: bool = False


@dataclass
class RepoManifestEntry:
    name: str
    tier: RepoTier
    role: str
    asset_class: str
    runtime_boundary: str
    permissions: RepoPermissions = field(default_factory=RepoPermissions)
    canonical_url: str = ""
    pinned_commit: str = ""
    license: str = ""
    review_verdict: str = ""
    sbom_status: str = "NOT_GENERATED"
    security_scan: str = "NOT_SCANNED"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "tier": self.tier.value,
            "role": self.role,
            "asset_class": self.asset_class,
            "runtime_boundary": self.runtime_boundary,
            "permissions": {
                "execution": self.permissions.execution,
                "network": self.permissions.network,
                "secrets": self.permissions.secrets,
                "production_import": self.permissions.production_import,
            },
            "canonical_url": self.canonical_url,
            "pinned_commit": self.pinned_commit,
            "license": self.license,
            "review_verdict": self.review_verdict,
            "sbom_status": self.sbom_status,
            "security_scan": self.security_scan,
        }


class RepoManifest:
    def __init__(self):
        self._entries: dict[str, RepoManifestEntry] = {}

    def add_entry(self, entry: RepoManifestEntry) -> None:
        self._entries[entry.name] = entry

    def get_entry(self, name: str) -> Optional[RepoManifestEntry]:
        return self._entries.get(name)

    def check_permission(self, name: str, perm: str) -> tuple[bool, str]:
        entry = self._entries.get(name)
        if entry is None:
            return False, f"NOT_IN_MANIFEST:{name}"
        if entry.tier in (RepoTier.Q, RepoTier.R):
            return False, f"TIER_BLOCKED:{entry.tier.value}"
        if perm == "execution" and not entry.permissions.execution:
            return False, "EXECUTION_DENIED"
        if perm == "network" and not entry.permissions.network:
            return False, "NETWORK_DENIED"
        if perm == "secrets" and not entry.permissions.secrets:
            return False, "SECRETS_DENIED"
        if perm == "production_import" and not entry.permissions.production_import:
            return False, "PRODUCTION_IMPORT_DENIED"
        return True, "ALLOWED"

    def list_entries(self) -> list[RepoManifestEntry]:
        return list(self._entries.values())

    def list_by_tier(self, tier: RepoTier) -> list[RepoManifestEntry]:
        return [e for e in self._entries.values() if e.tier == tier]

    def validate_all_entries(self) -> list[str]:
        issues = []
        for name, entry in self._entries.items():
            if not entry.canonical_url:
                issues.append(f"{name}: missing canonical_url")
            if not entry.pinned_commit:
                issues.append(f"{name}: missing pinned_commit")
            if entry.permissions.execution and entry.tier != RepoTier.A:
                issues.append(f"{name}: execution permission requires Tier A")
        return issues

    def to_yaml(self) -> str:
        data = [e.to_dict() for e in self._entries.values()]
        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    def save(self, path: str) -> None:
        Path(path).write_text(self.to_yaml())

    def load(self, path: str) -> None:
        if Path(path).exists():
            data = yaml.safe_load(Path(path).read_text())
            for item in data:
                entry = RepoManifestEntry(
                    name=item["name"],
                    tier=RepoTier(item["tier"]),
                    role=item["role"],
                    asset_class=item["asset_class"],
                    runtime_boundary=item["runtime_boundary"],
                    permissions=RepoPermissions(**item.get("permissions", {})),
                    canonical_url=item.get("canonical_url", ""),
                    pinned_commit=item.get("pinned_commit", ""),
                    license=item.get("license", ""),
                    review_verdict=item.get("review_verdict", ""),
                    sbom_status=item.get("sbom_status", "NOT_GENERATED"),
                    security_scan=item.get("security_scan", "NOT_SCANNED"),
                )
                self._entries[entry.name] = entry

    def fingerprint(self) -> str:
        """SHA-256 fingerprint of entire manifest state."""
        data = json.dumps([e.to_dict() for e in self._entries.values()], sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()
