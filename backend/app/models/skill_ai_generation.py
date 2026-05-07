"""
AI-Powered Skill Generation — Feature 11
Auto-generate skills from natural language, code, or examples
"""

import uuid
from datetime import datetime
from uuid import UUID as UUIDType

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as SQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AIGenerationRequest(Base):
    """
    Request for AI-powered skill generation

    Feature 11: AI-Powered Skill Generation
    """

    __tablename__ = "ai_generation_requests"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Request identification
    request_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    # Input sources (one or more)
    natural_language_prompt: Mapped[str | None] = mapped_column(Text)
    source_code: Mapped[str | None] = mapped_column(Text)
    example_inputs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    example_outputs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    reference_skill_ids: Mapped[list[UUIDType]] = mapped_column(JSONB, default=list)

    # Generation configuration
    skill_type: Mapped[str] = mapped_column(String(50), default="function")
    complexity_level: Mapped[str] = mapped_column(
        String(20), default="medium"
    )  # simple, medium, complex
    target_framework: Mapped[str | None] = mapped_column(
        String(50)
    )  # langchain, autogen, crewai, etc.

    # Constraints
    max_tokens: Mapped[int | None] = mapped_column(Integer)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    required_capabilities: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # Requester
    requested_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, generating, reviewing, completed, failed

    # Results
    generated_skill_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=True
    )
    generation_attempts: Mapped[int] = mapped_column(Integer, default=0)

    # Quality metrics
    quality_score: Mapped[int | None] = mapped_column(Integer)  # 0-100
    validation_passed: Mapped[bool | None] = mapped_column(Boolean)

    # Timestamps
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Error handling
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)


class AIGenerationTemplate(Base):
    """
    Templates for consistent AI skill generation
    """

    __tablename__ = "ai_generation_templates"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    template_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Template content
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_prompt_template: Mapped[str] = mapped_column(Text, nullable=False)

    # Template variables
    variables: Mapped[list[dict]] = mapped_column(
        JSONB, default=list
    )  # [{name, type, description, required}]

    # Template metadata
    skill_type: Mapped[str] = mapped_column(String(50), default="function")
    framework: Mapped[str | None] = mapped_column(String(50))

    # Usage
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    average_quality_score: Mapped[float | None] = mapped_column(Numeric(4, 2))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class AIGenerationFeedback(Base):
    """
    Feedback on AI-generated skills for improvement
    """

    __tablename__ = "ai_generation_feedback"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Related generation
    request_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("ai_generation_requests.id"), nullable=False, index=True
    )
    generated_skill_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=False
    )

    # Feedback
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    feedback_text: Mapped[str | None] = mapped_column(Text)

    # Specific issues
    issues: Mapped[list[str]] = mapped_column(
        JSONB, default=list
    )  # ["incorrect_logic", "poor_naming", "missing_error_handling"]

    # Improvement suggestions
    suggested_changes: Mapped[list[dict]] = mapped_column(
        JSONB, default=list
    )  # [{field, current, suggested}]

    # Feedback provider
    provided_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
