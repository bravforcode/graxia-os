import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "repo_intelligence"))

from hooks.pre_commit_check import run_check as pre_commit_check
from hooks.registry_check import run_check as registry_check


class TestPreCommitHook:
    def test_returns_zero_on_missing_manifest(self, monkeypatch):
        monkeypatch.setattr("os.path.exists", lambda x: False)
        assert pre_commit_check() == 0


class TestRegistryCheck:
    def test_returns_zero_on_missing_registry(self, monkeypatch):
        monkeypatch.setattr("os.path.exists", lambda x: False)
        assert registry_check() == 0
