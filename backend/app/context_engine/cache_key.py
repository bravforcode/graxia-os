"""Hash-aware cache keys for context packs."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

POLICY_VERSION = "2026-05-26"


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_git_commit_hash(root_path: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root_path,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None

    commit_hash = (result.stdout or "").strip()
    return commit_hash or None


def build_context_cache_key(
    *,
    task_type: str,
    goal: str,
    selected_paths: list[str],
    file_hashes: dict[str, str],
    compression_mode: str,
    policy_version: str = POLICY_VERSION,
    git_commit_hash: str | None = None,
) -> str:
    prompt_hash = hash_text(goal)
    normalized_paths = sorted(path.replace("\\", "/") for path in selected_paths)
    normalized_hashes = {
        path.replace("\\", "/"): file_hashes[path]
        for path in sorted(file_hashes)
    }
    raw = json.dumps(
        {
            "prompt_hash": prompt_hash,
            "task_type": task_type,
            "selected_paths": normalized_paths,
            "file_hashes": normalized_hashes,
            "git_commit_hash": git_commit_hash or "no-git",
            "compression_mode": compression_mode,
            "policy_version": policy_version,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
