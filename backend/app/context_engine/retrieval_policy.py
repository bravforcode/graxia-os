"""Retrieval policy — finds relevant files for a task type, keyword, or feature.

Selects files by path, keyword, feature name, task type, API route, model name,
service name, test name, or MCP tool name.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.context_engine.schemas import ProjectFileInfo, ProjectIndex

# Task type → feature keyword mapping
_TASK_FEATURE_MAP: dict[str, list[str]] = {
    "funnel_review": ["funnel", "product", "order", "delivery", "conversion"],
    "mcp_review": ["mcp", "tool", "registry"],
    "workspace_review": ["workspace", "google_workspace"],
    "context_engine_review": ["context_engine"],
    "security_review": ["approval", "auth", "permissions", "audit"],
    "test_failure_debug": ["test", "failure"],
    "implementation_plan": ["model", "service", "api", "schema"],
    "release_review": ["migration", "version", "changelog"],
}

# Feature → keyword mapping for file path matching
_FEATURE_KEYWORDS: dict[str, list[str]] = {
    "funnel": [
        "funnel", "product", "order", "delivery", "conversion",
        "lead_magnet", "lead_capture", "recommendation",
    ],
    "mcp": [
        "mcp/tool", "mcp/server", "mcp/registry", "mcp_permissions",
        "mcp_auth", "mcp_audit", "mcp_error",
    ],
    "workspace": [
        "google_workspace", "workspace.py",
        "mock_provider", "gmail", "docs", "sheets", "drive", "calendar",
    ],
    "approval": [
        "approval_request", "approval_flow", "approval",
        "write.py", "dangerous",
    ],
    "context": [
        "context_engine",
    ],
    "token": [
        "token", "optimization", "benchmark",
    ],
}


class RetrievalPolicy:
    """Selects relevant files based on task type, keywords, or feature names."""

    def retrieve(
        self,
        project_index: ProjectIndex,
        *,
        query: str | None = None,
        task_type: str | None = None,
        feature: str | None = None,
        max_results: int = 15,
    ) -> list[tuple[ProjectFileInfo, str]]:
        """Retrieve relevant files from the index.

        Returns list of (file_info, reason) tuples.
        """
        results: dict[str, tuple[ProjectFileInfo, str]] = {}

        # Get keywords from all sources
        keywords = set()
        if query:
            keywords.update(self._tokenize(query))
        if task_type and task_type in _TASK_FEATURE_MAP:
            for kw in _TASK_FEATURE_MAP[task_type]:
                keywords.add(kw)
        if feature and feature in _FEATURE_KEYWORDS:
            for kw in _FEATURE_KEYWORDS[feature]:
                keywords.add(kw)

        # Score each file
        for file_info in project_index.files:
            path_lower = file_info.path.lower()
            summary_lower = (file_info.summary or "").lower()
            score = 0
            reason = ""

            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in path_lower:
                    score += 10
                    reason = f"keyword match: {kw}"
                elif kw_lower in summary_lower:
                    score += 5
                    reason = f"summary match: {kw}"

            # Bonus for category match
            if task_type:
                category_key = task_type.replace("_review", "").replace("_debug", "")
                if category_key == file_info.category:
                    score += 3
                    reason = f"category match: {file_info.category}"

            if score > 0:
                results[file_info.path] = (file_info, reason)

        # Sort by score (highest first), limit results
        sorted_results = sorted(
            results.values(),
            key=lambda x: x[0].estimated_tokens if x[0].is_indexed else 99999,
        )
        sorted_results.sort(key=lambda x: self._match_score(x[0].path, keywords), reverse=True)

        return sorted_results[:max_results]

    def retrieve_by_path(
        self,
        project_index: ProjectIndex,
        path_substring: str,
    ) -> list[ProjectFileInfo]:
        """Retrieve files matching a path substring."""
        path_lower = path_substring.lower()
        matches = []
        for f in project_index.files:
            if path_lower in f.path.lower():
                matches.append(f)
        return matches[:20]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Tokenize a query string into keywords."""
        tokens = set()
        words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text)
        for word in words:
            tokens.add(word.lower())
            if word.endswith("s") and len(word) > 3:
                tokens.add(word[:-1].lower())
        return tokens

    @staticmethod
    def _match_score(path: str, keywords: set[str]) -> int:
        """Score a file path against keywords."""
        path_lower = path.lower()
        score = 0
        for kw in keywords:
            if kw.lower() in path_lower:
                score += 10
        return score

    @staticmethod
    def list_available_task_types() -> list[str]:
        return sorted(_TASK_FEATURE_MAP.keys())

    @staticmethod
    def list_available_features() -> list[str]:
        return sorted(_FEATURE_KEYWORDS.keys())
