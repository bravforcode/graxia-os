"""
Conversation Memory for Skills — Feature 14
Context-aware skill execution with conversation history
"""

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as SQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ConversationSession(Base):
    """
    A conversation session with context

    Feature 14: Conversation Memory
    """

    __tablename__ = "conversation_sessions"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Session identification
    session_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    # Session context
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)

    # Participants
    agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True, index=True
    )
    user_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Associated skills (for skill-specific conversations)
    primary_skill_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=True
    )

    # Session configuration
    max_context_messages: Mapped[int] = mapped_column(Integer, default=20)
    context_window_tokens: Mapped[int] = mapped_column(Integer, default=4000)

    # Memory settings
    enable_persistent_memory: Mapped[bool] = mapped_column(Boolean, default=True)
    memory_retention_days: Mapped[int] = mapped_column(Integer, default=30)

    # Session state
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, paused, archived

    # Summary (AI-generated)
    summary: Mapped[str | None] = mapped_column(Text)
    key_entities: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # Stats
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationMessage(Base):
    """
    Individual message in a conversation
    """

    __tablename__ = "conversation_messages"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Session reference
    session_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("conversation_sessions.id"), nullable=False, index=True
    )

    # Message metadata
    message_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Sender
    sender_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # user, agent, skill, system
    sender_id: Mapped[UUIDType | None] = mapped_column(SQLUUID(as_uuid=True), nullable=True)

    # Message content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(50), default="text"
    )  # text, code, json, image_url

    # Skill invocation context (if this message triggered a skill)
    invoked_skill_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=True
    )
    skill_input: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    skill_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Token usage
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)

    # Message context (what the model saw)
    context_included: Mapped[bool] = mapped_column(Boolean, default=True)
    context_messages: Mapped[list[int]] = mapped_column(
        JSONB, default=list
    )  # Message numbers included in context

    # Performance
    generation_duration_ms: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    __table_args__ = (
        Index(
            "ix_conversation_messages_session_number", "session_id", "message_number", unique=True
        ),
    )


class ConversationContextWindow(Base):
    """
    Pre-computed context windows for efficient retrieval
    """

    __tablename__ = "conversation_context_windows"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    session_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("conversation_sessions.id"), nullable=False, index=True
    )

    # Window configuration
    window_start_message: Mapped[int] = mapped_column(Integer, nullable=False)
    window_end_message: Mapped[int] = mapped_column(Integer, nullable=False)

    # Window content (serialized)
    messages_summary: Mapped[str] = mapped_column(Text)  # Condensed summary of messages
    key_facts: Mapped[list[dict]] = mapped_column(
        JSONB, default=list
    )  # [{fact, source_message, confidence}]

    # Token count
    total_tokens: Mapped[int] = mapped_column(Integer)

    # Relevance scoring
    relevance_scores: Mapped[dict[str, float]] = mapped_column(
        JSONB, default=dict
    )  # {topic: score}

    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ConversationMemoryExtract(Base):
    """
    Extracted facts and memories from conversations
    """

    __tablename__ = "conversation_memory_extracts"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    session_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("conversation_sessions.id"), nullable=False, index=True
    )

    # Extracted information
    fact_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # preference, entity, intent, relationship, task
    fact_key: Mapped[str] = mapped_column(String(255), nullable=False)
    fact_value: Mapped[str] = mapped_column(Text, nullable=False)

    # Source
    source_message_ids: Mapped[list[UUIDType]] = mapped_column(JSONB, default=list)
    extraction_confidence: Mapped[float] = mapped_column(Numeric(3, 2), default=0.8)

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Usage
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (Index("ix_memory_extracts_session_key", "session_id", "fact_key"),)


class SkillContextPreference(Base):
    """
    Agent preferences for skill execution context
    """

    __tablename__ = "skill_context_preferences"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Owner
    agent_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )

    # Skill (or default for all skills)
    skill_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=True
    )

    # Preferences
    default_context_variables: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict
    )  # {tone, language, verbosity, output_format}

    preferred_conversation_style: Mapped[str] = mapped_column(
        String(50), default="professional"
    )  # casual, professional, technical, concise

    # Auto-invocation settings
    auto_invoke_on_keywords: Mapped[list[str]] = mapped_column(JSONB, default=list)
    require_confirmation: Mapped[bool] = mapped_column(Boolean, default=True)

    # Memory settings
    remember_preferences: Mapped[bool] = mapped_column(Boolean, default=True)
    share_context_across_sessions: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("ix_context_preferences_agent_skill", "agent_id", "skill_id", unique=True),
    )
