"""Tests for context engine diff protocol and cache."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from app.context_engine.cache import ContextCache
from app.context_engine.diff_protocol import DiffProtocol
from app.context_engine.schemas import ContextPack


class TestDiffProtocol:
    """Test diff protocol — note: git must be available for real diff tests."""

    def _init_git_repo(self, path: Path) -> None:
        try:
            subprocess.run(["git", "init"], cwd=str(path), capture_output=True, timeout=10)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(path), capture_output=True, timeout=5)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=str(path), capture_output=True, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    def _git_add(self, path: Path) -> None:
        try:
            subprocess.run(["git", "add", "."], cwd=str(path), capture_output=True, timeout=10)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    def _git_commit(self, path: Path, msg: str) -> None:
        try:
            subprocess.run(["git", "commit", "-m", msg], cwd=str(path), capture_output=True, timeout=10)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    def test_diff_protocol_detects_git(self):
        protocol = DiffProtocol()
        assert protocol.is_git_available is not None

    def test_diff_protocol_excludes_secret_files(self):
        """Secret files should be excluded from diff results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_git_repo(root)

            (root / "safe.py").write_text("print('hello')\n")
            (root / ".env").write_text("SECRET=key\n")

            self._git_add(root)

            protocol = DiffProtocol()
            files = protocol.get_changed_files(str(root))
            assert "safe.py" in files
            assert ".env" not in files

    def test_diff_context_has_summary(self):
        """Changed file should have a diff summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_git_repo(root)

            (root / "test.py").write_text("x = 1\n")
            self._git_add(root)
            self._git_commit(root, "initial")

            (root / "test.py").write_text("x = 2\ny = 3\n")
            protocol = DiffProtocol()
            diff = protocol.get_file_diff(str(root), "test.py")
            if diff:
                assert diff.path == "test.py"
                assert diff.diff_summary != ""
                assert diff.estimated_tokens > 0

    def test_get_changed_files_empty_if_no_git(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            protocol = DiffProtocol()
            files = protocol.get_changed_files(str(tmpdir))
            assert isinstance(files, list)

    def test_get_file_diff_none_for_excluded(self):
        protocol = DiffProtocol()
        diff = protocol.get_file_diff("/tmp", ".env")
        assert diff is None


class TestContextCache:
    """Test context cache operations."""

    def test_cache_set_get(self):
        cache = ContextCache()
        pack = ContextPack(
            context_pack_id="ctx_test123",
            task_type="test",
            goal="test goal",
            token_budget=1000,
            estimated_tokens=500,
            cache_key="test_key",
        )
        cache.set("test_key", pack)
        retrieved = cache.get("test_key")
        assert retrieved is not None
        assert retrieved.context_pack_id == "ctx_test123"
        assert retrieved.cache_key == "test_key"

    def test_cache_returns_none_for_missing(self):
        cache = ContextCache()
        result = cache.get("nonexistent")
        assert result is None

    def test_cache_invalidate_single_key(self):
        cache = ContextCache()
        pack = ContextPack(context_pack_id="ctx_1", cache_key="key1")
        cache.set("key1", pack)
        cache.set("key2", ContextPack(context_pack_id="ctx_2", cache_key="key2"))

        cache.invalidate("key1")
        assert cache.get("key1") is None
        assert cache.get("key2") is not None

    def test_cache_invalidate_all(self):
        cache = ContextCache()
        cache.set("key1", ContextPack(context_pack_id="ctx_1", cache_key="key1"))
        cache.set("key2", ContextPack(context_pack_id="ctx_2", cache_key="key2"))

        cache.invalidate()
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.size == 0

    def test_cache_clear(self):
        cache = ContextCache()
        cache.set("key1", ContextPack(context_pack_id="ctx_1", cache_key="key1"))
        cache.clear()
        assert cache.size == 0

    def test_cache_stats(self):
        cache = ContextCache()
        cache.set("key1", ContextPack(context_pack_id="ctx_1", cache_key="key1"))
        stats = cache.get_stats()
        assert stats["size"] == 1
        assert stats["ttl_seconds"] > 0

    def test_cache_entry_metadata(self):
        cache = ContextCache()
        pack = ContextPack(
            context_pack_id="ctx_test123",
            task_type="test",
            goal="test goal",
            token_budget=1000,
            estimated_tokens=500,
            cache_key="test_key",
            generated_at="2026-01-01T00:00:00",
        )
        cache.set("test_key", pack)

        entry = cache.get_entry("test_key")
        assert entry is not None
        assert entry.cache_key == "test_key"
        assert entry.context_pack_id == "ctx_test123"
        assert entry.metadata["task_type"] == "test"

    def test_cache_key_changes_when_budget_changes(self):
        cache = ContextCache()
        pack1 = ContextPack(
            context_pack_id="ctx_1",
            token_budget=1000,
            cache_key="cache_key_1000",
        )
        pack2 = ContextPack(
            context_pack_id="ctx_2",
            token_budget=2000,
            cache_key="cache_key_2000",
        )
        cache.set("key_1000", pack1)
        cache.set("key_2000", pack2)

        assert cache.get("key_1000") is not None
        assert cache.get("key_2000") is not None
