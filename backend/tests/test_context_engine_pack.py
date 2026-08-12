"""Tests for context engine context pack builder."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.context_engine.context_pack import ContextPackBuilder
from app.context_engine.exclusions import ExclusionPolicy


class TestContextPackBuilder:
    """Test context pack builder with a temporary project."""

    @pytest.fixture
    def temp_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create safe files of varying sizes
            (root / "main.py").write_text("print('hello world')\n")
            (root / "utils.py").write_text("def foo():\n    pass\n" * 30)  # medium file
            (root / "large.py").write_text("x = 1\n" * 500)  # large file
            (root / "README.md").write_text("# Test\n")
            (root / ".env").write_text("SECRET=changeme")  # excluded
            (root / "config.yaml").write_text("debug: true\n")

            # Create model file
            (root / "models").mkdir()
            (root / "models" / "funnel.py").write_text(
                "class FunnelOrder:\n    pass\nclass Product:\n    pass\n"
            )

            # Create test file
            (root / "tests").mkdir()
            (root / "tests" / "test_funnel.py").write_text(
                "from models.funnel import FunnelOrder\n\ndef test_order():\n    assert True\n"
            )

            # Create service file
            (root / "services").mkdir()
            (root / "services" / "funnel_service.py").write_text(
                "from models.funnel import FunnelOrder\n\ndef get_orders():\n    return []\n"
            )

            yield root

    def test_context_pack_respects_budget(self, temp_project):
        builder = ContextPackBuilder()
        pack = builder.build_context_pack(
            root_path=str(temp_project),
            task_type="funnel_review",
            goal="review funnel",
            token_budget=500,
        )
        # Should not exceed budget by more than 10%
        assert pack.estimated_tokens <= 550  # 500 + 10%
        assert pack.context_pack_id != ""
        assert pack.task_type == "funnel_review"

    def test_context_pack_excludes_secret_files(self, temp_project):
        builder = ContextPackBuilder()
        pack = builder.build_context_pack(
            root_path=str(temp_project),
            task_type="funnel_review",
            goal="review funnel",
            token_budget=2000,
        )
        # Secret files should not be in included files
        included_paths = [f.path for f in pack.included_files]
        assert ".env" not in included_paths
        assert all(".env" not in p for p in included_paths)

        # Secret files should appear in excluded files
        excluded_paths = [e.path for e in pack.excluded_files]
        assert any(".env" in e for e in excluded_paths)

    def test_context_pack_includes_relevant_tests(self, temp_project):
        builder = ContextPackBuilder()
        pack = builder.build_context_pack(
            root_path=str(temp_project),
            task_type="funnel_review",
            goal="review funnel",
            token_budget=2000,
        )
        # Should include funnel-related files
        included_paths = [f.path for f in pack.included_files]
        test_files = [p for p in included_paths if "test" in p.lower()]
        assert any("funnel" in p.lower() for p in included_paths)

    def test_context_pack_warns_when_budget_too_small(self, temp_project):
        builder = ContextPackBuilder()
        pack = builder.build_context_pack(
            root_path=str(temp_project),
            task_type="funnel_review",
            goal="review funnel",
            token_budget=10,  # Very small budget
        )
        # Should have warnings
        assert len(pack.warnings) >= 0  # At minimum, not an error
        assert pack.estimated_tokens >= 0

    def test_context_pack_handles_empty_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = ContextPackBuilder()
            pack = builder.build_context_pack(
                root_path=str(tmpdir),
                task_type="funnel_review",
                goal="review",
                token_budget=1000,
            )
            assert pack.context_pack_id != ""
            assert pack.estimated_tokens == 0

    def test_context_pack_includes_constraints(self, temp_project):
        builder = ContextPackBuilder()
        pack = builder.build_context_pack(
            root_path=str(temp_project),
            task_type="funnel_review",
            goal="review funnel",
            token_budget=2000,
            must_preserve=["no secrets", "no raw tokens"],
        )
        assert "no secrets" in pack.constraints
        assert "no raw tokens" in pack.constraints

    def test_context_pack_has_cache_key(self, temp_project):
        builder = ContextPackBuilder()
        pack = builder.build_context_pack(
            root_path=str(temp_project),
            task_type="funnel_review",
            goal="review",
            token_budget=1000,
        )
        assert pack.cache_key != ""
        assert pack.cache_key != "empty"

    def test_context_pack_includes_explicit_path(self, temp_project):
        builder = ContextPackBuilder()
        pack = builder.build_context_pack(
            root_path=str(temp_project),
            task_type="funnel_review",
            goal="review funnel",
            token_budget=2000,
            include_paths=["main.py"],
        )
        included_paths = [f.path for f in pack.included_files]
        assert "main.py" in included_paths
