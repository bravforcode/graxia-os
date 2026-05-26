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
from app.context_engine.cache_key import build_context_cache_key, get_git_commit_hash
from app.context_engine.critical_policy import is_critical_path, is_aggressive_content_mode
from app.context_engine.quality_gate import QualityGateFinding, QualityGateResult, evaluate_context_pack
from app.context_engine.escalation import EscalationDecision, EscalationStage, decide_auto_escalation
from app.context_engine.multi_agent_registry import AgentContextRegistration, MultiAgentContextRegistry
from app.context_engine.token_roi import TokenRoiInput, TokenRoiResult, evaluate_token_roi

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
    "build_context_cache_key",
    "get_git_commit_hash",
    "is_critical_path",
    "is_aggressive_content_mode",
    "QualityGateFinding",
    "QualityGateResult",
    "evaluate_context_pack",
    "EscalationDecision",
    "EscalationStage",
    "decide_auto_escalation",
    "AgentContextRegistration",
    "MultiAgentContextRegistry",
    "TokenRoiInput",
    "TokenRoiResult",
    "evaluate_token_roi",
]
