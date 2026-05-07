"""SkillsMP Skill Model - AI Learning & Evolution System"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import (
    UUID as SQLUUID,
)
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class SkillsMPSkill(Base):
    """
    SkillsMP Skill Model with AI Learning & Evolution capabilities.

    This model stores skills from skillsmp.com with full support for:
    - Auto-sync from external API
    - AI self-improvement and skill evolution
    - Context-aware recommendations
    - Usage tracking and effectiveness scoring
    """

    __tablename__ = "skillsmp_skills"

    # Primary fields
    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    external_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # openclaw, claude, codex, hermes, tool, dev, context
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)  # Full markdown
    content_embedding: Mapped[list[float] | None] = mapped_column(
        JSONB, default=None
    )  # Vector embedding for RAG
    skill_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Learning & Evolution fields
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))  # 0-100%
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effectiveness_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    ai_improved_version: Mapped[str | None] = mapped_column(Text)  # AI-generated improvements

    # Auto-learning fields
    related_skill_ids: Mapped[list[UUIDType] | None] = mapped_column(
        JSONB, default=list
    )  # Connected skills
    trigger_patterns: Mapped[list[str] | None] = mapped_column(JSONB, default=list)  # When to use
    context_tags: Mapped[list[str] | None] = mapped_column(JSONB, default=list)  # Domain tags

    # Sync metadata
    first_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    auto_sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_deleted_at_source: Mapped[bool] = mapped_column(Boolean, default=False)

    # Version control
    version: Mapped[int] = mapped_column(Integer, default=1)
    previous_versions: Mapped[list[dict] | None] = mapped_column(
        JSONB, default=list
    )  # Track changes

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    learning_logs: Mapped[list["SkillLearningLog"]] = relationship(
        "SkillLearningLog", back_populates="skill", cascade="all, delete-orphan", lazy="selectin"
    )
    invocations: Mapped[list["SkillInvocation"]] = relationship(
        "SkillInvocation", back_populates="skill", lazy="selectin"
    )

    def update_usage_stats(self, success: bool, outcome_quality: float = 0.8) -> None:
        """Update usage statistics after invocation."""
        self.usage_count += 1
        self.last_used_at = datetime.now()

        # Exponential moving average for success rate
        alpha = Decimal("0.1")
        success_value = Decimal("100") if success else Decimal("0")
        self.success_rate = self.success_rate * (Decimal("1") - alpha) + success_value * alpha

        # Calculate effectiveness score
        usage_factor = min(Decimal(self.usage_count) / Decimal("100"), Decimal("1"))
        quality_factor = Decimal(str(outcome_quality)) * Decimal("30")

        self.effectiveness_score = (
            self.success_rate * Decimal("0.4") + usage_factor * Decimal("30") + quality_factor
        )

    def archive_current_version(self) -> None:
        """Archive current version before update."""
        if not self.previous_versions:
            self.previous_versions = []

        self.previous_versions.append(
            {
                "version": self.version,
                "content": self.content,
                "timestamp": datetime.now().isoformat(),
            }
        )
        self.version += 1

    def add_ai_improvement(self, improved_content: str) -> None:
        """Store AI-generated improvement."""
        self.archive_current_version()
        self.ai_improved_version = improved_content
        self.updated_at = datetime.now()

    def get_effective_content(self, prefer_improved: bool = True) -> str | None:
        """Get content - use AI-improved version if available and preferred."""
        if prefer_improved and self.ai_improved_version:
            return self.ai_improved_version
        return self.content

    def __repr__(self) -> str:
        return f"<SkillsMPSkill(id={self.id}, name='{self.name}', type='{self.source_type}')>"


class SkillLearningLog(Base):
    """Log of AI learning events for skills."""

    __tablename__ = "skill_learning_log"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    skill_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("skillsmp_skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    learning_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # usage, improvement, creation
    context: Mapped[str | None] = mapped_column(Text)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    skill: Mapped[SkillsMPSkill] = relationship("SkillsMPSkill", back_populates="learning_logs")


class SkillRecommendationCache(Base):
    """Cache for skill recommendations."""

    __tablename__ = "skill_recommendations"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    recommended_skill_ids: Mapped[list[UUIDType]] = mapped_column(JSONB, nullable=False)
    scores: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SkillInvocation(Base):
    """Track all skill invocations for analytics and learning."""

    __tablename__ = "skill_invocations"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    skill_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("skillsmp_skills.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invocation_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # direct, rag, content_injection
    task_context: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool | None] = mapped_column(Boolean)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer)
    feedback_rating: Mapped[int | None] = mapped_column(Integer)  # 1-5
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    skill: Mapped[SkillsMPSkill | None] = relationship(
        "SkillsMPSkill", back_populates="invocations"
    )
