"""Pydantic schemas for SkillsMP API"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ============== Base Schemas ==============


class SkillsMPSkillBase(BaseModel):
    """Base skill schema."""

    name: str
    description: str | None = None
    content: str | None = None
    source_type: str  # openclaw, claude, codex, hermes, tool, dev, context
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillsMPSkillOut(BaseModel):
    """Skill output schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_id: str
    source_type: str
    name: str
    description: str | None = None
    content_preview: str | None = None  # First 500 chars
    metadata: dict[str, Any]

    # Learning stats
    usage_count: int
    success_rate: Decimal
    effectiveness_score: Decimal
    last_used_at: datetime | None = None

    # Auto-learning
    context_tags: list[str] = Field(default_factory=list)
    trigger_patterns: list[str] = Field(default_factory=list)
    related_skill_ids: list[UUID] = Field(default_factory=list)

    # Version control
    version: int
    has_ai_improvement: bool = False

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_synced_at: datetime | None = None

    @classmethod
    def from_orm(cls, skill):
        """Create from ORM model with computed fields."""
        data = {
            "id": skill.id,
            "external_id": skill.external_id,
            "source_type": skill.source_type,
            "name": skill.name,
            "description": skill.description,
            "content_preview": (skill.content or "")[:500] + "..."
            if skill.content and len(skill.content) > 500
            else skill.content,
            "metadata": skill.skill_metadata or {},
            "usage_count": skill.usage_count or 0,
            "success_rate": skill.success_rate or Decimal("0"),
            "effectiveness_score": skill.effectiveness_score or Decimal("0"),
            "last_used_at": skill.last_used_at,
            "context_tags": skill.context_tags or [],
            "trigger_patterns": skill.trigger_patterns or [],
            "related_skill_ids": skill.related_skill_ids or [],
            "version": skill.version or 1,
            "has_ai_improvement": bool(skill.ai_improved_version),
            "created_at": skill.created_at,
            "updated_at": skill.updated_at,
            "last_synced_at": skill.last_synced_at,
        }
        return cls(**data)


class SkillsMPSkillDetailOut(SkillsMPSkillOut):
    """Detailed skill output with full content."""

    content: str | None = None
    ai_improved_content: str | None = None
    previous_versions: list[dict[str, Any]] = Field(default_factory=list)


class SkillsMPSkillList(BaseModel):
    """List of skills with pagination."""

    total: int
    items: list[SkillsMPSkillOut]
    page: int = 1
    limit: int = 50


# ============== Recommendation Schemas ==============


class SkillRecommendationOut(BaseModel):
    """Skill recommendation output."""

    skill_id: UUID
    name: str
    skill_type: str
    description: str | None = None
    content_preview: str
    score: Decimal
    effectiveness: Decimal
    usage_count: int
    match_reasons: dict[str, float]
    trigger_match: str | None = None


class SkillRecommendationRequest(BaseModel):
    """Request for skill recommendations."""

    task_context: str
    current_skill_ids: list[UUID] = Field(default_factory=list)
    preferred_types: list[str] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1, le=20)


class SkillRecommendationResponse(BaseModel):
    """Response for skill recommendations."""

    recommendations: list[SkillRecommendationOut]
    query: str
    total_found: int


class SkillChainOut(BaseModel):
    """Skill chain output."""

    skills: list[SkillRecommendationOut]
    total_score: Decimal
    chain_reason: str


class SkillGapOut(BaseModel):
    """Identified skill gap."""

    skill_type: str
    reason: str
    suggestion: str


class SkillDiscoverResponse(BaseModel):
    """Response for skill discovery."""

    recommended_skills: list[SkillRecommendationOut]
    skill_gaps: list[SkillGapOut]
    suggested_learning: list[dict[str, Any]]


# ============== Invocation Schemas ==============


class SkillInvokeRequest(BaseModel):
    """Request to invoke a skill."""

    skill_id: UUID
    task: str
    context: str | None = None
    model: str | None = None  # Override default model
    prefer_improved: bool = True  # Use AI-improved version if available
    temperature: float = 0.7
    max_tokens: int | None = None


class SkillInvokeResponse(BaseModel):
    """Response from skill invocation."""

    skill_id: UUID
    skill_name: str
    skill_type: str
    response: str
    model_used: str
    usage: dict[str, int]  # prompt_tokens, completion_tokens, total_tokens
    skill_effectiveness: Decimal
    execution_time_ms: int


class SkillContentRequest(BaseModel):
    """Request for skill content."""

    prefer_improved: bool = True
    include_history: bool = False


class SkillContentResponse(BaseModel):
    """Response with skill content."""

    id: UUID
    name: str
    skill_type: str
    content: str
    is_improved_version: bool
    version: int
    metadata: dict[str, Any]
    effectiveness_score: Decimal
    previous_versions: list[dict[str, Any]] | None = None


class SkillFeedbackRequest(BaseModel):
    """Request to submit skill feedback."""

    rating: int = Field(ge=1, le=5)  # 1-5
    feedback_text: str | None = None
    context: str | None = None


class SkillFeedbackResponse(BaseModel):
    """Response after submitting feedback."""

    skill_id: UUID
    new_effectiveness: Decimal
    new_success_rate: Decimal
    improvement_triggered: bool
    message: str


# ============== Search Schemas ==============


class SkillSearchRequest(BaseModel):
    """Request to search skills."""

    query: str
    context: str | None = None
    skill_type: str | None = None
    min_effectiveness: float = Field(default=0, ge=0, le=100)
    limit: int = Field(default=10, ge=1, le=50)
    use_rag: bool = True


class SkillSearchResponse(BaseModel):
    """Response for skill search."""

    query: str
    context: str | None = None
    results: list[SkillRecommendationOut]
    total_found: int
    suggested_chain: SkillChainOut | None = None


# ============== Sync Schemas ==============


class SyncTriggerRequest(BaseModel):
    """Request to trigger sync."""

    full_sync: bool = True
    skill_types: list[str] = Field(default_factory=list)


class SyncTriggerResponse(BaseModel):
    """Response after triggering sync."""

    status: str
    job_id: str | None = None
    message: str
    estimated_duration_seconds: int


class SyncStatusResponse(BaseModel):
    """Response for sync status."""

    last_sync: datetime | None = None
    next_scheduled: datetime | None = None
    is_running: bool
    total_skills: int
    by_type: dict[str, dict[str, Any]]
    ai_improved: int
    high_effectiveness: int  # Score >= 70
    recent_stats: dict[str, Any] | None = None


# ============== Learning Schemas ==============


class LearningLogOut(BaseModel):
    """Learning log output."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    learning_type: str
    context: str | None = None
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    confidence_score: Decimal | None = None
    created_at: datetime | None = None


class SkillAnalysisRequest(BaseModel):
    """Request to analyze skills."""

    skill_type: str | None = None
    min_usage: int = Field(default=5, ge=0)
    generate_improvements: bool = False


class SkillAnalysisResponse(BaseModel):
    """Response for skill analysis."""

    total_analyzed: int
    high_performers: int
    needs_improvement: int
    candidates_for_ai_improvement: int
    improvements_generated: int
    by_type: dict[str, dict[str, Any]]
    recommendations: list[str]


class SkillImprovementRequest(BaseModel):
    """Request to generate improvement for a skill."""

    skill_id: UUID


class SkillImprovementResponse(BaseModel):
    """Response after generating improvement."""

    skill_id: UUID
    skill_name: str
    improvement_generated: bool
    improvement_reason: str | None = None
    changes_summary: list[str] = Field(default_factory=list)
    new_version: int
    confidence_score: Decimal | None = None


# ============== Type/category Schemas ==============


class SkillTypesResponse(BaseModel):
    """Response with available skill types."""

    types: list[str]
    counts: dict[str, int]


class SkillCategoriesResponse(BaseModel):
    """Response with skill categories/tags."""

    tags: dict[str, int]  # Tag name -> count
    total_tags: int
