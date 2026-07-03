"""Context Engine Service — facade that coordinates indexer, pack builder, cache, diff protocol, and graph.

Provides a unified API for building context packs, searching context,
getting summaries, and managing cache.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.context_engine.cache import ContextCache
from app.context_engine.context_graph import ContextGraphBuilder
from app.context_engine.context_pack import ContextPackBuilder
from app.context_engine.diff_protocol import DiffProtocol
from app.context_engine.exclusions import ExclusionPolicy
from app.context_engine.project_indexer import ProjectIndexer
from app.context_engine.quality_gate import evaluate_context_pack
from app.context_engine.retrieval_policy import RetrievalPolicy
from app.context_engine.schemas import (
    ContextGraph,
    ContextPack,
    ProjectIndex,
)

logger = logging.getLogger(__name__)


class ContextEngineService:
    """Facade for all context engine operations.

    Coordinates:
    - Project indexing (ProjectIndexer)
    - Context pack building (ContextPackBuilder)
    - Context caching (ContextCache)
    - Diff protocol (DiffProtocol)
    - Context graph (ContextGraphBuilder)
    - Retrieval policy (RetrievalPolicy)
    """

    def __init__(
        self,
        root_path: str | None = None,
        exclusion_policy: ExclusionPolicy | None = None,
        cache: ContextCache | None = None,
    ) -> None:
        self.root_path = root_path or ""
        self.exclusion_policy = exclusion_policy or ExclusionPolicy()
        self.cache = cache or ContextCache()
        self.project_indexer = ProjectIndexer(exclusion_policy=self.exclusion_policy)
        self.retrieval_policy = RetrievalPolicy()
        self.diff_protocol = DiffProtocol(exclusion_policy=self.exclusion_policy)
        self.context_pack_builder = ContextPackBuilder(
            exclusion_policy=self.exclusion_policy,
            retrieval_policy=self.retrieval_policy,
            diff_protocol=self.diff_protocol,
        )
        self.context_graph_builder = ContextGraphBuilder()
        self._last_index: ProjectIndex | None = None

    def build_index(self, root_path: str | None = None, max_files: int = 5000) -> ProjectIndex:
        """Build a fresh project index."""
        rp = root_path or self.root_path
        self._last_index = self.project_indexer.build_index(rp, max_files=max_files)
        return self._last_index

    def build_context_pack(
        self,
        task_type: str,
        goal: str,
        token_budget: int = 4000,
        query: str | None = None,
        include_paths: list[str] | None = None,
        must_preserve: list[str] | None = None,
        root_path: str | None = None,
        use_cache: bool = True,
    ) -> ContextPack:
        """Build a context pack, optionally from cache."""
        rp = root_path or self.root_path

        if use_cache and self.cache:
            # Build cache key and check cache
            from app.context_engine.context_pack import ContextPackBuilder
            cache_key = ContextPackBuilder._build_cache_key(  # type: ignore[attr-defined]
                root_path=rp,
                task_type=task_type,
                goal=goal,
                token_budget=token_budget,
                query=query,
                include_paths=include_paths,
                must_preserve=must_preserve,
            )
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.info("Context pack cache HIT: task=%s", task_type)
                return cached

        pack = self.context_pack_builder.build_context_pack(
            root_path=rp,
            task_type=task_type,
            goal=goal,
            token_budget=token_budget,
            query=query,
            include_paths=include_paths,
            must_preserve=must_preserve,
        )

        gate = evaluate_context_pack(
            pack,
            required_paths=include_paths or None,
            expected_error_text=query if task_type == "test_failure_debug" and query else None,
        )
        if not gate.passed:
            pack.warnings.extend(f"{finding.code}: {finding.message}" for finding in gate.findings)

        # Store in cache
        if use_cache and self.cache and pack.cache_key:
            self.cache.set(pack.cache_key, pack)

        return pack

    def search_context(
        self,
        query: str,
        max_results: int = 10,
        root_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search project context by keyword."""
        rp = root_path or self.root_path
        index = self._last_index or self.build_index(rp)

        results = self.retrieval_policy.retrieve(
            index, query=query, max_results=max_results,
        )

        items = []
        for file_info, reason in results:
            items.append({
                "path": file_info.path,
                "category": file_info.category,
                "estimated_tokens": file_info.estimated_tokens,
                "summary": file_info.summary or "",
                "reason": reason,
            })

        return items

    def get_index_summary(self, root_path: str | None = None) -> dict[str, Any]:
        """Get summary of the current project index."""
        rp = root_path or self.root_path
        index = self._last_index or self.build_index(rp)

        # Count categories
        categories: dict[str, int] = {}
        for f in index.files:
            categories[f.category] = categories.get(f.category, 0) + 1

        return {
            "total_files_seen": index.total_files_seen,
            "total_files_indexed": index.total_files_indexed,
            "total_files_excluded": index.total_files_excluded,
            "total_estimated_tokens": index.total_estimated_tokens,
            "top_categories": dict(sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10]),
            "warnings": index.warnings,
            "root_path": index.root_path,
            "generated_at": index.generated_at,
        }

    def get_changed_files(self, root_path: str | None = None) -> list[str]:
        """Get list of changed files from git."""
        rp = root_path or self.root_path
        return self.diff_protocol.get_changed_files(rp)

    def get_diff_context(
        self, file_path: str, root_path: str | None = None,
    ) -> dict[str, Any] | None:
        """Get diff context for a single file."""
        rp = root_path or self.root_path
        diff = self.diff_protocol.get_file_diff(rp, file_path)
        if diff is None:
            return None
        return {
            "path": diff.path,
            "estimated_tokens": diff.estimated_tokens,
            "diff_summary": diff.diff_summary,
            "diff_text": diff.diff_text or "",
            "truncated": (diff.diff_text or "") != (diff.diff_text or ""),
        }

    def estimate_tokens(self, text: str) -> dict[str, int]:
        """Estimate tokens for a text string."""
        from app.context_engine.token_estimator import estimate_text_tokens

        return {
            "estimated_tokens": estimate_text_tokens(text),
            "character_count": len(text) if text else 0,
        }

    def get_context_pack(self, context_pack_id: str) -> ContextPack | None:
        """Get a context pack by ID from cache."""
        for entry in self.cache._metadata.values():  # type: ignore[attr-defined]
            if entry.context_pack_id == context_pack_id:
                return self.cache.get(entry.cache_key)
        return None

    def invalidate_cache(self, cache_key: str | None = None) -> dict[str, Any]:
        """Invalidate context cache."""
        self.cache.invalidate(cache_key)
        return {
            "invalidated": True,
            "cache_key": cache_key or "all",
            "remaining_entries": self.cache.size,
        }

    def build_context_graph(self, root_path: str | None = None) -> ContextGraph:
        """Build a context graph from the project index."""
        rp = root_path or self.root_path
        index = self._last_index or self.build_index(rp)
        return self.context_graph_builder.build_from_index(index)
