"""Diff protocol — detects and summarizes changed files using git.

Uses git when available, returns safe warnings otherwise.
Never includes excluded file diffs.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from app.context_engine.exclusions import ExclusionPolicy
from app.context_engine.schemas import DiffContext
from app.context_engine.token_estimator import estimate_text_tokens

logger = logging.getLogger(__name__)

_MAX_DIFF_LINES = 500


class DiffProtocol:
    """Detects and summarizes changed files using git.

    Falls back gracefully if git is unavailable.
    """

    def __init__(self, exclusion_policy: ExclusionPolicy | None = None) -> None:
        self.exclusion_policy = exclusion_policy or ExclusionPolicy()
        self._git_available: bool | None = None

    @property
    def is_git_available(self) -> bool:
        """Check if git is available in the environment."""
        if self._git_available is not None:
            return self._git_available
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            self._git_available = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            self._git_available = False
        return self._git_available

    def get_changed_files(self, root_path: str) -> list[str]:
        """Get list of changed files (unstaged + uncommitted).

        Returns [] with warning if git is unavailable.
        Excludes secret files.
        """
        if not self.is_git_available:
            logger.info("Git not available for diff protocol.")
            return []

        try:
            result = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True, text=True, timeout=30,
                cwd=root_path,
            )
            if result.returncode != 0:
                logger.warning("Git diff failed: %s", result.stderr[:200])
                return []

            files = [f.strip() for f in result.stdout.split("\n") if f.strip()]

            # Also include uncommitted tracked files
            result2 = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True, text=True, timeout=30,
                cwd=root_path,
            )
            if result2.returncode == 0:
                cached = [f.strip() for f in result2.stdout.split("\n") if f.strip()]
                files.extend(f for f in cached if f not in files)

            # Filter excluded files
            safe_files = []
            for f in files:
                excluded, _ = self.exclusion_policy.should_exclude(Path(f))
                if not excluded:
                    safe_files.append(f)

            return safe_files

        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("Git diff error: %s", exc)
            return []

    def get_file_diff(self, root_path: str, file_path: str) -> DiffContext | None:
        """Get diff context for a single file.

        Returns None if:
        - File is excluded by policy
        - Git is unavailable
        - File has no diff
        """
        # Exclude check
        excluded, reason = self.exclusion_policy.should_exclude(Path(file_path))
        if excluded:
            return None

        if not self.is_git_available:
            return None

        try:
            # Get diff for working tree
            result = subprocess.run(
                ["git", "diff", "--", file_path],
                capture_output=True, text=True, timeout=30,
                cwd=root_path,
            )
            diff_text = result.stdout

            # Also try staged diff
            result2 = subprocess.run(
                ["git", "diff", "--cached", "--", file_path],
                capture_output=True, text=True, timeout=30,
                cwd=root_path,
            )
            if result2.stdout:
                if diff_text:
                    diff_text += "\n" + result2.stdout
                else:
                    diff_text = result2.stdout

            if not diff_text.strip():
                return None

            # Truncate if too long
            truncated = False
            lines = diff_text.split("\n")
            if len(lines) > _MAX_DIFF_LINES:
                diff_text = "\n".join(lines[:_MAX_DIFF_LINES]) + "\n... (truncated)"
                truncated = True

            # Get old hash (current HEAD version)
            try:
                hash_result = subprocess.run(
                    ["git", "hash-object", file_path],
                    capture_output=True, text=True, timeout=15,
                    cwd=root_path,
                )
                new_hash = hash_result.stdout.strip() if hash_result.returncode == 0 else ""
            except (subprocess.TimeoutExpired, OSError):
                new_hash = ""

            diff_summary = self.summarize_diff(diff_text)

            return DiffContext(
                path=file_path,
                old_hash=None,
                new_hash=new_hash,
                diff_summary=diff_summary,
                diff_text=diff_text if not truncated else diff_text,
                estimated_tokens=estimate_text_tokens(diff_text),
            )

        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("Git diff error for %s: %s", file_path, exc)
            return None

    @staticmethod
    def summarize_diff(diff_text: str) -> str:
        """Summarize a diff text into a one-line description.

        Counts added/deleted lines and detects changed files.
        """
        lines = diff_text.split("\n")
        added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        deleted = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        changed_files = []
        for l in lines:
            if l.startswith("diff --git"):
                parts = l.split(" b/")
                if len(parts) > 1:
                    changed_files.append(parts[-1])

        summary_parts = []
        if changed_files:
            summary_parts.append(f"files: {', '.join(changed_files[:3])}")
        if added > 0 or deleted > 0:
            summary_parts.append(f"+{added}/-{deleted} lines")
        summary_parts.append(f"{len(lines)} diff lines")

        return " | ".join(summary_parts) if summary_parts else "no changes"
