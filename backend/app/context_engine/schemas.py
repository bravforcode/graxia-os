"""Context Engine — data contracts / schemas.

All dataclasses used by the context engine: file info, index, graph, pack, diff, cache.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── File Info ────────────────────────────────────────────────────────────────

@dataclass
class ProjectFileInfo:
    """Metadata about a single project file."""

    path: str
    language: str | None = None
    size_bytes: int = 0
    estimated_tokens: int = 0
    sha256: str = ""
    modified_at: str | None = None
    category: str = "unknown"
    is_indexed: bool = False
    excluded_reason: str | None = None
    summary: str | None = None


# ── Project Index ────────────────────────────────────────────────────────────

@dataclass
class ProjectIndex:
    """Full index of a project directory."""

    root_path: str = ""
    generated_at: str = ""
    total_files_seen: int = 0
    total_files_indexed: int = 0
    total_files_excluded: int = 0
    total_estimated_tokens: int = 0
    files: list[ProjectFileInfo] = field(default_factory=list)
    excluded: list[ProjectFileInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── Context Graph ────────────────────────────────────────────────────────────

@dataclass
class ContextGraphNode:
    """A node in the context graph (file, api route, service, model, etc.)."""

    id: str
    type: str = "file"
    label: str = ""
    path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextGraphEdge:
    """An edge relating two context graph nodes."""

    source: str
    target: str
    relation: str = "imports"
    confidence: float = 1.0


@dataclass
class ContextGraph:
    """A graph of context relationships across the project."""

    nodes: list[ContextGraphNode] = field(default_factory=list)
    edges: list[ContextGraphEdge] = field(default_factory=list)
    generated_at: str = ""


# ── Context Pack ─────────────────────────────────────────────────────────────

@dataclass
class ContextPackFile:
    """A file included in a context pack."""

    path: str
    sha256: str = ""
    estimated_tokens: int = 0
    inclusion_reason: str = "relevant"
    content_mode: str = "metadata_only"  # full | summary | diff | metadata_only
    content: str | None = None
    summary: str | None = None


@dataclass
class ContextSummary:
    """A summary entry in a context pack."""

    path: str = ""
    summary: str = ""
    estimated_tokens: int = 0


@dataclass
class ExcludedFile:
    """A file excluded from a context pack."""

    path: str = ""
    reason: str = ""


@dataclass
class DiffContext:
    """Diff information for a changed file."""

    path: str = ""
    old_hash: str | None = None
    new_hash: str = ""
    diff_summary: str = ""
    diff_text: str | None = None
    estimated_tokens: int = 0


@dataclass
class ContextPack:
    """A complete context pack — a token-budgeted selection of files, summaries, and diffs."""

    context_pack_id: str = ""
    task_type: str = ""
    goal: str = ""
    token_budget: int = 4000
    estimated_tokens: int = 0
    generated_at: str = ""
    root_path: str = ""
    must_preserve: list[str] = field(default_factory=list)
    included_files: list[ContextPackFile] = field(default_factory=list)
    summaries: list[ContextSummary] = field(default_factory=list)
    diffs: list[DiffContext] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    excluded_files: list[ExcludedFile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cache_key: str = ""


# ── Cache Entry ──────────────────────────────────────────────────────────────

@dataclass
class ContextCacheEntry:
    """A single entry in the context cache."""

    cache_key: str = ""
    context_pack_id: str = ""
    created_at: str = ""
    expires_at: str | None = None
    input_hash: str = ""
    output_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
