import sys
import os
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'repo_intelligence'))

from hooks.pre_commit_check import run_check as pre_commit_check
from hooks.registry_check import run_check as registry_check


def write_file(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


class TestPreCommitHook:
    def test_fails_closed_on_missing_canonical_registry(self, tmp_path):
        registry_path = tmp_path / "missing_repositories_canonical.yml"
        assert pre_commit_check(str(registry_path)) == 1

    def test_fails_closed_on_invalid_canonical_registry_yaml(self, tmp_path):
        registry_path = write_file(tmp_path / "repositories_canonical.yml", "repositories: [\n")
        assert pre_commit_check(str(registry_path)) == 1

    def test_fails_closed_on_empty_canonical_registry(self, tmp_path):
        registry_path = write_file(tmp_path / "repositories_canonical.yml", "repositories: []\n")
        assert pre_commit_check(str(registry_path)) == 1

    def test_returns_zero_for_valid_canonical_registry(self, tmp_path):
        registry_path = write_file(
            tmp_path / "repositories_canonical.yml",
            """\
repositories:
  - repo_id: approved_repo
    canonical_url: https://example.com/approved_repo.git
    owner: example
    name: approved_repo
    asset_scope: Forex research
    language: Python
    license_spdx: MIT
    pinned_commit: abc123
    observed_at_utc: "2026-06-22T00:00:00Z"
    allowed_role: APPROVED_DIFFERENTIAL_ORACLE
    execution_permission: true
    credential_permission: false
    network_permission: false
    quarantine_status: false
""",
        )
        assert pre_commit_check(str(registry_path)) == 0

class TestRegistryCheck:
    def test_fails_closed_on_missing_registry(self, tmp_path):
        registry_path = tmp_path / "missing_registry.yml"
        assert registry_check(str(registry_path)) == 1

    def test_fails_closed_on_invalid_registry_yaml(self, tmp_path):
        registry_path = write_file(tmp_path / "repositories_canonical.yml", "repositories: [\n")
        assert registry_check(str(registry_path)) == 1

    def test_fails_closed_on_missing_required_registry_fields(self, tmp_path):
        registry_path = write_file(
            tmp_path / "repositories_canonical.yml",
            """\
repositories:
  - repo_id: approved_repo
    canonical_url: https://example.com/approved_repo.git
    owner: example
    name: approved_repo
    asset_scope: Forex research
    language: Python
    license_spdx: MIT
    pinned_commit: abc123
    observed_at_utc: "2026-06-22T00:00:00Z"
    execution_permission: true
    credential_permission: false
    network_permission: false
    quarantine_status: false
""",
        )
        assert registry_check(str(registry_path)) == 1

    def test_returns_zero_for_valid_registry(self, tmp_path):
        registry_path = write_file(
            tmp_path / "repositories_canonical.yml",
            """\
repositories:
  - repo_id: approved_repo
    canonical_url: https://example.com/approved_repo.git
    owner: example
    name: approved_repo
    asset_scope: Forex research
    language: Python
    license_spdx: MIT
    pinned_commit: abc123
    observed_at_utc: "2026-06-22T00:00:00Z"
    allowed_role: APPROVED_DIFFERENTIAL_ORACLE
    execution_permission: true
    credential_permission: false
    network_permission: false
    quarantine_status: false
""",
        )
        assert registry_check(str(registry_path)) == 0
