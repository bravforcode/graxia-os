"""Context pack builder — selects files, summaries, and diffs within a token budget.

Respects exclusions, must_preserve constraints, and budget limits.
Prefer summaries over full content when budget is tight.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.context_engine.diff_protocol import DiffProtocol
from app.context_engine.exclusions import ExclusionPolicy
from app.context_engine.retrieval_policy import RetrievalPolicy
from app.context_engine.cache_key import build_context_cache_key, get_git_commit_hash
from app.context_engine.critical_policy import is_critical_path
from app.context_engine.schemas import (
    ContextPack,
    ContextPackFile,
    ContextSummary,
    DiffContext,
    ExcludedFile,
    ProjectFileInfo,
    ProjectIndex,
)
from app.context_engine.token_estimator import estimate_file_tokens, estimate_text_tokens

logger = logging.getLogger(__name__)

_MAX_BUDGET_OVERAGE = 0.10  # Allow up to 10% over budget


class ContextPackBuilder:
    """Builds token-budgeted context packs from project indices.

    Selection rules:
    1. Always include explicitly requested safe files if within budget.
    2. Always include must_preserve items as constraints.
    3. Prefer summaries over full contents when budget is tight.
    4. Never include excluded files.
    5. Never exceed token_budget by more than 10%.
    6. Add warning if budget is too small.
    7. Include tests relevant to selected implementation files.
    """

    def __init__(
        self,
        exclusion_policy: ExclusionPolicy | None = None,
        retrieval_policy: RetrievalPolicy | None = None,
        diff_protocol: DiffProtocol | None = None,
    ) -> None:
        self.exclusion_policy = exclusion_policy or ExclusionPolicy()
        self.retrieval_policy = retrieval_policy or RetrievalPolicy()
        self.diff_protocol = diff_protocol or DiffProtocol()

    def build_context_pack(
        self,
        root_path: str,
        task_type: str,
        goal: str,
        token_budget: int = 4000,
        query: str | None = None,
        include_paths: list[str] | None = None,
        must_preserve: list[str] | None = None,
    ) -> ContextPack:
        """Build a context pack for the given task.

        Selects files from a freshly built project index, respecting budget and exclusions.
        """
        root = Path(root_path).resolve()
        warnings: list[str] = []
        included_files: list[ContextPackFile] = []
        summaries: list[ContextSummary] = []
        diffs: list[DiffContext] = []
        excluded_files: list[ExcludedFile] = []
        total_estimated = 0
        budget_limit = int(token_budget * (1 + _MAX_BUDGET_OVERAGE))

        # Build project index
        from app.context_engine.project_indexer import ProjectIndexer

        indexer = ProjectIndexer(exclusion_policy=self.exclusion_policy)
        project_index = indexer.build_index(str(root))

        if not project_index.files and not project_index.excluded:
            warnings.append("No files found in project root.")
            return self._empty_pack(
                root_path=str(root), task_type=task_type, goal=goal,
                token_budget=token_budget, warnings=warnings,
            )

        # Collect constraints
        constraints: list[str] = list(must_preserve or [])
        if "no secrets" not in constraints:
            constraints.append("no secrets")
        if "no raw tokens" not in constraints:
            constraints.append("no raw tokens")

        # Collect commands for task type
        commands = self._get_commands_for_task(task_type)

        # 1. Handle explicitly requested paths
        if include_paths:
            for inc_path in include_paths:
                matched = self._find_file_by_path(project_index, inc_path)
                if matched:
                    include_mode = "full" if is_critical_path(matched.path) else "full"
                    inc_pack = self._file_to_pack_file(matched, root, mode=include_mode)
                    inc_tokens = inc_pack.estimated_tokens
                    if total_estimated + inc_tokens <= budget_limit:
                        included_files.append(inc_pack)
                        total_estimated += inc_tokens
                    else:
                        # Try summary mode instead
                        inc_pack_summary = self._file_to_pack_file(matched, root, mode="summary")
                        if (
                            not is_critical_path(matched.path)
                            and total_estimated + inc_pack_summary.estimated_tokens <= budget_limit
                        ):
                            included_files.append(inc_pack_summary)
                            total_estimated += inc_pack_summary.estimated_tokens
                        else:
                            if is_critical_path(matched.path):
                                warnings.append(f"Critical path could not fit as full content: {matched.path}")
                            included_files.append(self._file_to_pack_file(matched, root, mode="metadata_only"))
                else:
                    warnings.append(f"Requested path not found in index: {inc_path}")

        # 2. Retrieve relevant files from policy
        relevant = self.retrieval_policy.retrieve(
            project_index,
            query=query,
            task_type=task_type,
            max_results=30,
        )

        for file_info, reason in relevant:
            if any(f.path == file_info.path for f in included_files):
                continue

            # Determine content mode based on file size and remaining budget
            remaining = token_budget - total_estimated

            if file_info.estimated_tokens <= 0:
                mode = "metadata_only"
            elif is_critical_path(file_info.path):
                mode = "full" if total_estimated + file_info.estimated_tokens <= budget_limit else "metadata_only"
                if mode != "full":
                    warnings.append(f"Critical path downgraded due to budget pressure: {file_info.path}")
            elif file_info.estimated_tokens <= 200 and remaining >= file_info.estimated_tokens:
                mode = "full"
            elif file_info.estimated_tokens <= 800 and remaining >= file_info.estimated_tokens:
                mode = "summary"
            else:
                mode = "metadata_only"

            pack_file = self._file_to_pack_file(file_info, root, mode=mode)

            if total_estimated + pack_file.estimated_tokens <= budget_limit:
                included_files.append(pack_file)
                total_estimated += pack_file.estimated_tokens

                if pack_file.summary:
                    summaries.append(ContextSummary(
                        path=file_info.path,
                        summary=pack_file.summary,
                        estimated_tokens=estimate_text_tokens(pack_file.summary),
                    ))
            else:
                # Budget exceeded — add as metadata only
                metadata_pack = self._file_to_pack_file(file_info, root, mode="metadata_only")
                if metadata_pack.estimated_tokens > 0:
                    included_files.append(metadata_pack)
                    total_estimated += metadata_pack.estimated_tokens

        # 3. Add diffs for changed files
        try:
            changed = self.diff_protocol.get_changed_files(str(root))
            for changed_path in changed:
                diff_ctx = self.diff_protocol.get_file_diff(str(root), changed_path)
                if diff_ctx and diff_ctx.estimated_tokens > 0:
                    remaining = token_budget - total_estimated
                    if diff_ctx.estimated_tokens <= remaining:
                        diffs.append(diff_ctx)
                        total_estimated += diff_ctx.estimated_tokens
        except Exception as exc:
            warnings.append(f"Diff protocol error: {exc}")

        # 4. Add excluded files list
        for excl_file in project_index.excluded:
            excluded_files.append(ExcludedFile(
                path=excl_file.path,
                reason=excl_file.excluded_reason or "excluded by policy",
            ))

        # Budget warnings
        if total_estimated > token_budget:
            warnings.append(f"Context pack exceeds budget ({total_estimated} > {token_budget}). Consider increasing token_budget or narrowing scope.")
        elif len(project_index.files) > 0 and len(included_files) == 0:
            warnings.append("No files could be included within the given token budget. Try increasing token_budget.")

        # Build cache key
        cache_key = build_context_cache_key(
            task_type=task_type,
            goal=goal,
            selected_paths=[file.path for file in included_files],
            file_hashes={file.path: file.sha256 for file in included_files if file.sha256},
            compression_mode=self._infer_compression_mode(included_files, diffs),
            git_commit_hash=get_git_commit_hash(str(root)),
        )

        return ContextPack(
            context_pack_id=f"ctx_{uuid4().hex[:12]}",
            task_type=task_type,
            goal=goal,
            token_budget=token_budget,
            estimated_tokens=total_estimated,
            generated_at=datetime.now(UTC).isoformat(),
            root_path=str(root),
            must_preserve=must_preserve or [],
            included_files=included_files,
            summaries=summaries,
            diffs=diffs,
            constraints=constraints,
            commands=commands,
            excluded_files=excluded_files,
            warnings=warnings,
            cache_key=cache_key,
        )

    def _file_to_pack_file(
        self,
        file_info: ProjectFileInfo,
        root: Path,
        mode: str = "metadata_only",
    ) -> ContextPackFile:
        """Convert a ProjectFileInfo to a ContextPackFile with optional content."""
        pack_file = ContextPackFile(
            path=file_info.path,
            sha256=file_info.sha256,
            estimated_tokens=file_info.estimated_tokens,
            inclusion_reason=file_info.summary or "",
            content_mode=mode,
            summary=file_info.summary,
        )

        if mode == "full" or mode == "summary":
            try:
                full_path = root / file_info.path
                content = full_path.read_text(encoding="utf-8", errors="replace")
                if mode == "summary":
                    lines = content.split("\n")
                    max_lines = min(50, len(lines))
                    pack_file.content = "\n".join(lines[:max_lines])
                    pack_file.estimated_tokens = estimate_text_tokens(pack_file.content)
                else:
                    pack_file.content = content
                    pack_file.estimated_tokens = estimate_text_tokens(content)
            except (OSError, UnicodeDecodeError):
                pack_file.content = None
        elif mode == "metadata_only":
            pack_file.content = None
            pack_file.estimated_tokens = max(1, min(file_info.estimated_tokens, 50))

        return pack_file

    @staticmethod
    def _find_file_by_path(index: ProjectIndex, search_path: str) -> ProjectFileInfo | None:
        """Find a file in the index by path substring."""
        search_lower = search_path.lower().replace("\\", "/")
        for f in index.files:
            if search_lower in f.path.lower():
                return f
        return None

    @staticmethod
    def _get_commands_for_task(task_type: str) -> list[str]:
        """Get relevant commands for a task type."""
        commands_map: dict[str, list[str]] = {
            "funnel_review": [
                "pytest backend/tests/test_funnel_v5.py -q",
                "pytest backend/tests/test_funnel_foundation.py -q",
            ],
            "mcp_review": [
                "pytest backend/tests/test_mcp_foundation.py -q",
                "pytest backend/tests/test_mcp_readonly_tools.py -q",
                "pytest backend/tests/test_mcp_approval_tools.py -q",
            ],
            "workspace_review": [
                "pytest backend/tests/test_workspace_mock_provider.py -q",
                "pytest backend/tests/test_mcp_workspace_tools.py -q",
            ],
            "context_engine_review": [
                "pytest backend/tests/test_context_engine_indexer.py -q",
                "pytest backend/tests/test_context_engine_pack.py -q",
            ],
            "security_review": [
                "pytest backend/tests/test_mcp_approval_tools.py -q",
                "pytest backend/tests/test_mcp_dangerous_tools.py -q",
            ],
            "test_failure_debug": [
                "pytest -q --tb=short",
            ],
            "implementation_plan": [
                "alembic heads",
                "python -m compileall backend/app",
            ],
            "release_review": [
                "git log --oneline -10",
                "alembic heads",
            ],
        }
        return commands_map.get(task_type, [])

    @staticmethod
    def _build_cache_key(
        root_path: str,
        task_type: str,
        goal: str,
        token_budget: int,
        query: str | None,
        include_paths: list[str] | None,
        must_preserve: list[str] | None,
    ) -> str:
        """Legacy deterministic request key for service pre-cache lookups."""
        raw = json.dumps(
            {
                "root_path": root_path,
                "task_type": task_type,
                "goal": goal,
                "token_budget": token_budget,
                "query": query,
                "include_paths": sorted(include_paths) if include_paths else [],
                "must_preserve": sorted(must_preserve) if must_preserve else [],
                "policy_version": 1,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _infer_compression_mode(
        included_files: list[ContextPackFile], diffs: list[DiffContext],
    ) -> str:
        modes = {file.content_mode for file in included_files}
        if modes == {"full"} and not diffs:
            return "none"
        if modes and modes.issubset({"full", "diff"}):
            return "diff"
        if "summary" in modes:
            return "summary"
        return "compact"

    @staticmethod
    def _empty_pack(
        root_path: str,
        task_type: str,
        goal: str,
        token_budget: int,
        warnings: list[str],
    ) -> ContextPack:
        return ContextPack(
            context_pack_id=f"ctx_{uuid4().hex[:12]}",
            task_type=task_type,
            goal=goal,
            token_budget=token_budget,
            estimated_tokens=0,
            generated_at=datetime.now(UTC).isoformat(),
            root_path=root_path,
            warnings=warnings,
            cache_key="empty",
        )
