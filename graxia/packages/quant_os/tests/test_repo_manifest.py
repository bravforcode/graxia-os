import pytest
from repo_intelligence.manifest import (
    RepoManifest, RepoManifestEntry, RepoTier, RepoPermissions
)
import tempfile, os


class TestRepoManifest:
    def _make_entry(self, name="test_repo", tier=RepoTier.C):
        return RepoManifestEntry(
            name=name,
            tier=tier,
            role="research",
            asset_class="strategy",
            runtime_boundary="backtest",
            permissions=RepoPermissions(),
            canonical_url="https://github.com/test/repo",
            pinned_commit="abc123",
            license="MIT",
        )

    def test_add_and_get(self):
        manifest = RepoManifest()
        entry = self._make_entry()
        manifest.add_entry(entry)
        assert manifest.get_entry("test_repo") is not None

    def test_not_in_manifest(self):
        manifest = RepoManifest()
        allowed, msg = manifest.check_permission("nonexistent", "execution")
        assert allowed is False
        assert "NOT_IN_MANIFEST" in msg

    def test_tier_q_blocked(self):
        manifest = RepoManifest()
        entry = self._make_entry(tier=RepoTier.Q)
        manifest.add_entry(entry)
        allowed, msg = manifest.check_permission("test_repo", "execution")
        assert allowed is False
        assert "TIER_BLOCKED" in msg

    def test_tier_r_blocked(self):
        manifest = RepoManifest()
        entry = self._make_entry(tier=RepoTier.R)
        manifest.add_entry(entry)
        allowed, msg = manifest.check_permission("test_repo", "network")
        assert allowed is False

    def test_execution_denied_by_default(self):
        manifest = RepoManifest()
        entry = self._make_entry()
        manifest.add_entry(entry)
        allowed, msg = manifest.check_permission("test_repo", "execution")
        assert allowed is False
        assert "EXECUTION_DENIED" in msg

    def test_network_denied_by_default(self):
        manifest = RepoManifest()
        entry = self._make_entry()
        manifest.add_entry(entry)
        allowed, msg = manifest.check_permission("test_repo", "network")
        assert allowed is False

    def test_secrets_denied_by_default(self):
        manifest = RepoManifest()
        entry = self._make_entry()
        manifest.add_entry(entry)
        allowed, msg = manifest.check_permission("test_repo", "secrets")
        assert allowed is False

    def test_list_by_tier(self):
        manifest = RepoManifest()
        manifest.add_entry(self._make_entry("a", RepoTier.A))
        manifest.add_entry(self._make_entry("b", RepoTier.B))
        manifest.add_entry(self._make_entry("c", RepoTier.C))
        a_entries = manifest.list_by_tier(RepoTier.A)
        assert len(a_entries) == 1
        assert a_entries[0].name == "a"

    def test_validate_missing_url(self):
        manifest = RepoManifest()
        entry = self._make_entry()
        entry.canonical_url = ""
        manifest.add_entry(entry)
        issues = manifest.validate_all_entries()
        assert any("missing canonical_url" in i for i in issues)

    def test_validate_missing_commit(self):
        manifest = RepoManifest()
        entry = self._make_entry()
        entry.pinned_commit = ""
        manifest.add_entry(entry)
        issues = manifest.validate_all_entries()
        assert any("missing pinned_commit" in i for i in issues)

    def test_fingerprint_deterministic(self):
        manifest = RepoManifest()
        manifest.add_entry(self._make_entry())
        f1 = manifest.fingerprint()
        f2 = manifest.fingerprint()
        assert f1 == f2

    def test_save_and_load(self):
        manifest = RepoManifest()
        manifest.add_entry(self._make_entry())
        with tempfile.NamedTemporaryFile(suffix='.yml', delete=False) as f:
            manifest.save(f.name)
            manifest2 = RepoManifest()
            manifest2.load(f.name)
            assert manifest2.get_entry("test_repo") is not None
        os.unlink(f.name)

    def test_to_dict(self):
        entry = self._make_entry()
        d = entry.to_dict()
        assert d["tier"] == "C"
        assert d["permissions"]["execution"] is False
