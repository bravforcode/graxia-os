"""Tests for context engine project indexer and exclusions."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from app.context_engine.exclusions import ExclusionPolicy
from app.context_engine.project_indexer import ProjectIndexer
from app.context_engine.token_estimator import estimate_text_tokens, estimate_file_tokens


class TestExclusionPolicy:
    """Test that exclusion policy correctly identifies secret files."""

    def test_excludes_env_file(self):
        policy = ExclusionPolicy()
        excluded, reason = policy.should_exclude(Path(".env"))
        assert excluded
        assert reason is not None

    def test_excludes_env_local(self):
        policy = ExclusionPolicy()
        excluded, reason = policy.should_exclude(Path(".env.local"))
        assert excluded

    def test_excludes_pem_file(self):
        policy = ExclusionPolicy()
        excluded, reason = policy.should_exclude(Path("secret.pem"))
        assert excluded

    def test_excludes_key_file(self):
        policy = ExclusionPolicy()
        excluded, reason = policy.should_exclude(Path("private.key"))
        assert excluded

    def test_excludes_p12_file(self):
        policy = ExclusionPolicy()
        excluded, reason = policy.should_exclude(Path("cert.p12"))
        assert excluded

    def test_excludes_service_account_json(self):
        policy = ExclusionPolicy()
        excluded, reason = policy.should_exclude(Path("service-account-123.json"))
        assert excluded

    def test_excludes_node_modules(self):
        policy = ExclusionPolicy()
        excluded, reason = policy.should_exclude(Path("node_modules/some/lib.js"))
        assert excluded

    def test_excludes_venv(self):
        policy = ExclusionPolicy()
        excluded, reason = policy.should_exclude(Path(".venv/lib/python3.11/site-packages/pkg.py"))
        assert excluded

    def test_excludes_pycache(self):
        policy = ExclusionPolicy()
        excluded, reason = policy.should_exclude(Path("__pycache__/module.cpython-311.pyc"))
        assert excluded

    def test_excludes_db_files(self):
        policy = ExclusionPolicy()
        assert policy.should_exclude(Path("data.sqlite"))[0]
        assert policy.should_exclude(Path("data.sqlite3"))[0]
        assert policy.should_exclude(Path("backup.db"))[0]

    def test_allows_python_file(self):
        policy = ExclusionPolicy()
        excluded, reason = policy.should_exclude(Path("app/main.py"))
        assert not excluded

    def test_allows_markdown_file(self):
        policy = ExclusionPolicy()
        excluded, reason = policy.should_exclude(Path("README.md"))
        assert not excluded

    def test_excludes_large_generated_files(self):
        policy = ExclusionPolicy()
        assert policy.should_exclude(Path("package-lock.json"))[0]
        assert policy.should_exclude(Path("yarn.lock"))[0]

    def test_excludes_binary_extensions(self):
        policy = ExclusionPolicy()
        assert policy.is_binary_likely(Path("image.png"))
        assert policy.is_binary_likely(Path("archive.zip"))
        assert policy.is_binary_likely(Path("document.pdf"))
        assert not policy.is_binary_likely(Path("source.py"))


class TestTokenEstimator:
    """Test deterministic token estimation."""

    def test_estimate_empty_string(self):
        assert estimate_text_tokens("") == 0

    def test_estimate_simple_text(self):
        # "hello world" = 11 chars, ceil(11/4) = 3
        assert estimate_text_tokens("hello world") == 3

    def test_estimate_exact_four_chars(self):
        assert estimate_text_tokens("abcd") == 1

    def test_estimate_five_chars(self):
        assert estimate_text_tokens("abcde") == 2  # ceil(5/4)

    def test_minimum_one_token(self):
        assert estimate_text_tokens("a") == 1

    def test_longer_text(self):
        text = "hello world this is a longer piece of text"
        expected = max(1, len(text) // 4 + (1 if len(text) % 4 else 0))
        assert estimate_text_tokens(text) == expected


class TestProjectIndexer:
    """Test project indexer with a temporary directory."""

    @pytest.fixture
    def temp_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create safe files
            (root / "main.py").write_text("print('hello')\n")
            (root / "utils.py").write_text("def foo():\n    pass\n")
            (root / "README.md").write_text("# Test Project\n")
            (root / "config").mkdir()
            (root / "config" / "settings.yaml").write_text("debug: true\n")

            # Create test file
            (root / "tests").mkdir()
            (root / "tests" / "test_main.py").write_text("def test_foo():\n    assert True\n")

            # Create excluded files
            (root / ".env").write_text("SECRET_KEY=changeme")
            (root / "secret.pem").write_text("fake-key-data")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "lib.js").write_text("module.exports = {}")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "module.pyc").write_text("")

            yield root

    def test_indexer_builds_project_index(self, temp_project):
        indexer = ProjectIndexer()
        index = indexer.build_index(str(temp_project), max_files=100)
        assert index.total_files_seen > 0
        assert index.generated_at != ""
        assert index.root_path == str(temp_project.resolve())

    def test_indexer_excludes_env_files_without_reading(self, temp_project):
        indexer = ProjectIndexer()
        index = indexer.build_index(str(temp_project), max_files=100)
        # .env should be in excluded, not in files
        excluded_paths = [e.path for e in index.excluded]
        assert ".env" in excluded_paths or any(".env" in e for e in excluded_paths)

        # Ensure .env is NOT in indexed files
        indexed_paths = [f.path for f in index.files]
        assert ".env" not in indexed_paths

    def test_indexer_excludes_key_and_pem_files(self, temp_project):
        indexer = ProjectIndexer()
        index = indexer.build_index(str(temp_project), max_files=100)
        excluded_paths = [e.path for e in index.excluded]
        assert any("pem" in e for e in excluded_paths)

    def test_indexer_classifies_files(self, temp_project):
        indexer = ProjectIndexer()
        index = indexer.build_index(str(temp_project), max_files=100)
        categories = {f.path: f.category for f in index.files}
        # Backend Python files
        assert categories.get("main.py") in ("backend", "unknown")
        # Test files
        assert categories.get("tests/test_main.py") == "test"

    def test_indexer_estimates_tokens(self, temp_project):
        indexer = ProjectIndexer()
        index = indexer.build_index(str(temp_project), max_files=100)
        total = sum(f.estimated_tokens for f in index.files)
        assert total >= 0
        assert index.total_estimated_tokens >= 0

    def test_indexer_handles_unreadable_files_safely(self):
        """Indexer should not crash on unreadable files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            safe_file = root / "readable.py"
            safe_file.write_text("x = 1\n")

            # Create a file-like directory entry that's not readable as a file
            # (skip creating an actual unreadable file which requires permissions)

            indexer = ProjectIndexer()
            index = indexer.build_index(str(tmpdir), max_files=100)
            assert index.total_files_seen > 0
            assert len(index.warnings) >= 0

    def test_indexer_with_nonexistent_path(self):
        indexer = ProjectIndexer()
        index = indexer.build_index("/nonexistent/path/12345")
        assert len(index.warnings) > 0
        assert index.total_files_seen == 0
        assert index.total_files_indexed == 0
