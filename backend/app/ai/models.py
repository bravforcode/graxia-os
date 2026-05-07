"""
AI Module Models - Pydantic schemas for AI endpoints
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════
# Chat Models
# ═══════════════════════════════════════════════════════════════


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    name: str | None = None  # For tool responses
    tool_calls: list[dict[str, Any]] | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = Field(default="auto", description="Model to use (auto = smart routing)")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=128000)
    stream: bool = Field(default=False)
    context: dict[str, Any] | None = Field(default=None, description="Additional context")
    use_vault: bool = Field(default=True, description="Include vault context")
    use_skills: bool = Field(default=True, description="Include relevant skills")


class ChatResponse(BaseModel):
    message: ChatMessage
    model_used: str
    tokens_used: int | None = None
    finish_reason: str | None = None
    context_references: list[str] | None = None


# ═══════════════════════════════════════════════════════════════
# Code Generation Models
# ═══════════════════════════════════════════════════════════════


class CodeLanguage(StrEnum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    SQL = "sql"
    BASH = "bash"
    POWERSHELL = "powershell"
    YAML = "yaml"
    JSON = "json"
    MARKDOWN = "markdown"


class CodeRequest(BaseModel):
    prompt: str = Field(..., description="What code to generate")
    language: CodeLanguage
    context: str | None = Field(default=None, description="Additional context/code")
    existing_code: str | None = Field(default=None, description="Code to modify/extend")
    include_tests: bool = Field(default=True)
    include_docs: bool = Field(default=True)
    style_guide: str | None = Field(default=None, description="Style guide to follow")


class CodeResponse(BaseModel):
    code: str
    language: CodeLanguage
    explanation: str
    tests: str | None = None
    documentation: str | None = None
    model_used: str
    suggestions: list[str] | None = None


# ═══════════════════════════════════════════════════════════════
# Code Fix Models
# ═══════════════════════════════════════════════════════════════


class CodeFixRequest(BaseModel):
    code: str
    error_message: str | None = None
    error_log: str | None = None
    language: CodeLanguage
    context: str | None = None
    auto_apply: bool = Field(default=False, description="Auto-apply fix if confident")


class CodeFixResponse(BaseModel):
    original_code: str
    fixed_code: str
    changes_made: list[str]
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)
    tests_suggested: list[str] | None = None
    auto_applied: bool = False


# ═══════════════════════════════════════════════════════════════
# Vault Query Models
# ═══════════════════════════════════════════════════════════════


class VaultQueryRequest(BaseModel):
    query: str
    search_type: Literal["semantic", "keyword", "graph"] = "semantic"
    limit: int = Field(default=10, ge=1, le=100)
    include_content: bool = Field(default=True)
    categories: list[str] | None = None
    tags: list[str] | None = None


class VaultFile(BaseModel):
    path: str
    name: str
    relevance_score: float
    content_preview: str | None = None
    tags: list[str] | None = None
    last_modified: datetime | None = None


class VaultQueryResponse(BaseModel):
    query: str
    total_results: int
    files: list[VaultFile]
    graph_context: dict[str, Any] | None = None
    skills_suggested: list[str] | None = None


# ═══════════════════════════════════════════════════════════════
# Task Delegation Models
# ═══════════════════════════════════════════════════════════════


class AgentType(StrEnum):
    HERMES = "hermes"  # Task planning
    MERCURY = "mercury"  # Code analysis
    ATHENA = "athena"  # Knowledge
    HEPHAESTUS = "hephaestus"  # DevOps
    N8N = "n8n"  # Workflows


class DelegateRequest(BaseModel):
    task: str
    to_agent: AgentType
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    context: dict[str, Any] | None = None
    callback_url: str | None = None
    deadline: datetime | None = None


class DelegateResponse(BaseModel):
    task_id: str
    assigned_to: AgentType
    status: Literal["queued", "in_progress", "completed", "failed"]
    estimated_completion: datetime | None = None
    result_preview: str | None = None
    full_result_url: str | None = None


# ═══════════════════════════════════════════════════════════════
# Agent Status Models
# ═══════════════════════════════════════════════════════════════


class AgentStatus(BaseModel):
    agent: AgentType
    online: bool
    current_load: int = Field(ge=0, le=100)
    capabilities: list[str]
    last_seen: datetime
    version: str | None = None


class AgentNetworkStatus(BaseModel):
    orchestrator: str = "openclaude"
    agents: list[AgentStatus]
    messages_in_queue: int
    recent_errors: list[str]


# ═══════════════════════════════════════════════════════════════
# Skill Management Models
# ═══════════════════════════════════════════════════════════════


class SkillLoadRequest(BaseModel):
    skill_id: str
    include_content: bool = Field(default=True)


class SkillInfo(BaseModel):
    id: str
    name: str
    description: str
    category: str
    family: str
    tags: list[str]
    estimated_tokens: int
    path: str


class SkillSearchRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=20)
    category: str | None = None


class SkillSearchResponse(BaseModel):
    query: str
    total_matches: int
    skills: list[SkillInfo]


# ═══════════════════════════════════════════════════════════════
# WebSocket Models
# ═══════════════════════════════════════════════════════════════


class WSMessageType(StrEnum):
    CHAT = "chat"
    CODE_REQUEST = "code_request"
    VAULT_SEARCH = "vault_search"
    AGENT_COMMAND = "agent_command"
    STATUS = "status"
    ERROR = "error"
    PROGRESS = "progress"


class WSMessage(BaseModel):
    type: WSMessageType
    id: str | None = None
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WSResponse(BaseModel):
    type: WSMessageType
    request_id: str | None = None
    payload: dict[str, Any]
    done: bool = Field(default=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════
# Analytics Models
# ═══════════════════════════════════════════════════════════════


class AIUsageMetrics(BaseModel):
    total_requests: int
    total_tokens_used: int
    average_response_time_ms: float
    models_used: dict[str, int]  # model -> count
    errors_count: int
    top_queries: list[str]


class VaultHealthMetrics(BaseModel):
    total_files: int
    orphaned_files: int
    broken_links: int
    missing_frontmatter: int
    tasks_pending: int
    tasks_completed: int
    last_optimization: datetime | None = None
