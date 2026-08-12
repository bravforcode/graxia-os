from __future__ import annotations

import tempfile
from pathlib import Path

from app.context_engine.cache_key import build_context_cache_key, hash_file


def test_cache_key_changes_when_file_hash_changes() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "service.py"
        file_path.write_text("print('v1')\n", encoding="utf-8")
        hash_v1 = hash_file(file_path)
        key_v1 = build_context_cache_key(
            task_type="test_failure_debug",
            goal="fix runtime failure",
            selected_paths=["service.py"],
            file_hashes={"service.py": hash_v1},
            compression_mode="compact",
            git_commit_hash=None,
        )

        file_path.write_text("print('v2')\n", encoding="utf-8")
        hash_v2 = hash_file(file_path)
        key_v2 = build_context_cache_key(
            task_type="test_failure_debug",
            goal="fix runtime failure",
            selected_paths=["service.py"],
            file_hashes={"service.py": hash_v2},
            compression_mode="compact",
            git_commit_hash=None,
        )
        assert key_v1 != key_v2


def test_cache_key_safe_without_git() -> None:
    key = build_context_cache_key(
        task_type="context_engine_review",
        goal="review context engine",
        selected_paths=["backend/app/context_engine/service.py"],
        file_hashes={"backend/app/context_engine/service.py": "abc123"},
        compression_mode="summary",
        git_commit_hash=None,
    )
    assert len(key) == 24
