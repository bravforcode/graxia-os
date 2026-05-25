"""Context Engine — Token-efficient context management for MCP agents.

Provides project indexing, context pack building, diff protocol,
secret-safe exclusions, token estimation, context graph, cache, and MCP tools.
"""
from __future__ import annotations

from app.context_engine.errors import (
    ContextEngineError,
    ExclusionError,
    IndexError,
    PackError,
    CacheError,
    DiffError,
    GraphError,
)
from app.context_engine.schemas import (
    ProjectFileInfo,
    ProjectIndex,
    ContextGraphNode,
    ContextGraphEdge,
    ContextGraph,
    ContextPack,
    ContextPackFile,
    DiffContext,
    ContextCacheEntry,
    ContextSummary,
    ExcludedFile,
)
from app.context_engine.exclusions import ExclusionPolicy
from app.context_engine.token_estimator import estimate_text_tokens, estimate_file_tokens, estimate_json_tokens
from app.context_engine.project_indexer import ProjectIndexer
from app.context_engine.context_graph import ContextGraphBuilder
from app.context_engine.retrieval_policy import RetrievalPolicy
from app.context_engine.context_pack import ContextPackBuilder
from app.context_engine.diff_protocol import DiffProtocol
from app.context_engine.cache import ContextCache
from app.context_engine.service import ContextEngineService

__all__ = [
    "ContextEngineError",
    "ExclusionError",
    "IndexError",
    "PackError",
    "CacheError",
    "DiffError",
    "GraphError",
    "ProjectFileInfo",
    "ProjectIndex",
    "ContextGraphNode",
    "ContextGraphEdge",
    "ContextGraph",
    "ContextPack",
    "ContextPackFile",
    "DiffContext",
    "ContextCacheEntry",
    "ContextSummary",
    "ExcludedFile",
    "ExclusionPolicy",
    "estimate_text_tokens",
    "estimate_file_tokens",
    "estimate_json_tokens",
    "ProjectIndexer",
    "ContextGraphBuilder",
    "RetrievalPolicy",
    "ContextPackBuilder",
    "DiffProtocol",
    "ContextCache",
    "ContextEngineService",
]
