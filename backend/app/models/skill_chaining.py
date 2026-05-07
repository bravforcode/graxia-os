"""
Skill Chaining and Composition — Feature 12
Chain multiple skills together for complex workflows
"""

import uuid
from datetime import datetime
from typing import Any
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


class SkillChain(Base):
    """
    A chain of skills executed in sequence

    Feature 12: Skill Chaining
    """

    __tablename__ = "skill_chains"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Chain identification
    chain_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Chain structure
    steps: Mapped[list[dict]] = mapped_column(
        JSONB, default=list
    )  # [{step_number, skill_id, input_mapping, output_mapping, condition}]

    # Input/Output schema
    input_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict
    )  # {field_name: {type, required, description}}
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Configuration
    is_parallel: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # Execute steps in parallel where possible
    max_execution_time_ms: Mapped[int | None] = mapped_column(Integer)
    retry_failed_steps: Mapped[bool] = mapped_column(Boolean, default=True)

    # Error handling
    on_step_failure: Mapped[str] = mapped_column(
        String(50), default="stop"
    )  # stop, continue, retry
    fallback_skill_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=True
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)

    # Ownership
    created_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    # Usage stats
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    average_execution_time_ms: Mapped[float | None] = mapped_column(Numeric(10, 2))
    success_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class SkillChainExecution(Base):
    """
    Execution record for a skill chain
    """

    __tablename__ = "skill_chain_executions"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Chain reference
    chain_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skill_chains.id"), nullable=False, index=True
    )

    # Execution details
    execution_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # Input/Output
    input_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Step results
    step_results: Mapped[list[dict]] = mapped_column(
        JSONB, default=list
    )  # [{step_number, skill_id, status, input, output, duration_ms, error}]

    # Performance
    total_duration_ms: Mapped[int | None] = mapped_column(Integer)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="running"
    )  # running, completed, failed, timeout

    # Error handling
    failed_step_number: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)

    # Execution context
    executed_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    execution_context: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=dict
    )  # {request_id, session_id, source}

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SkillComposition(Base):
    """
    Compose multiple skills into a single composite skill
    """

    __tablename__ = "skill_compositions"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Composition identification
    composition_key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Resulting skill
    composite_skill_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=False, unique=True
    )

    # Component skills
    component_skills: Mapped[list[dict]] = mapped_column(
        JSONB, default=list
    )  # [{skill_id, role, weight, required}]

    # Composition strategy
    composition_type: Mapped[str] = mapped_column(
        String(50), default="sequential"
    )  # sequential, parallel, conditional, loop

    # Data flow configuration
    data_mappings: Mapped[list[dict]] = mapped_column(
        JSONB, default=list
    )  # [{from_skill, to_skill, field_mapping}]

    # Version control
    version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    parent_composition_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skill_compositions.id"), nullable=True
    )

    # Metadata
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class SkillChainTemplate(Base):
    """
    Reusable templates for common skill chains
    """

    __tablename__ = "skill_chain_templates"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    template_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100), index=True)

    # Template structure
    template_steps: Mapped[list[dict]] = mapped_column(
        JSONB, default=list
    )  # [{step_type, skill_placeholder, configuration}]

    # Variable placeholders
    variables: Mapped[list[dict]] = mapped_column(
        JSONB, default=list
    )  # [{name, type, description, default_value}]

    # Template metadata
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Usage
    usage_count: Mapped[int] = mapped_column(Integer, default=0)

    created_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
