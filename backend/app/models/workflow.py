"""
Automation & Workflow Models — Features 56-70
Workflow engine, pipelines, triggers, and orchestration
"""

import uuid
from datetime import datetime
from enum import StrEnum
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
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# ═══════════════════════════════════════════════════════════════════════════════
# WORKFLOW — Workflow definitions (Features 56-59)
# ═══════════════════════════════════════════════════════════════════════════════


class WorkflowStatus(StrEnum):
    """Workflow status."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"
    ERROR = "error"


class MarketplaceListingStatus(StrEnum):
    """Marketplace listing status."""

    PENDING = "pending"
    ACTIVE = "active"
    SOLD = "sold"
    INACTIVE = "inactive"


class Workflow(Base):
    """
    Workflow Definition

    Features:
    - 56: Auto-Skill Assignment
    - 57: Skill-Based Routing
    - 58: Skill Triggers
    - 59: Skill Workflows
    """

    __tablename__ = "workflows"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Workflow Type
    workflow_type: Mapped[str] = mapped_column(
        String(50), default="automation"
    )  # automation, orchestration, pipeline, scheduled

    # Configuration
    status: Mapped[str] = mapped_column(String(50), default=WorkflowStatus.DRAFT)
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Entry Point
    entry_skill_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=True
    )

    # Flow Definition (DAG)
    flow_definition: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=dict
    )  # {nodes: [], edges: []}

    # Input/Output Schema
    input_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Settings
    is_parallel: Mapped[bool] = mapped_column(Boolean, default=False)
    max_parallel_branches: Mapped[int] = mapped_column(Integer, default=5)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    retry_count: Mapped[int] = mapped_column(Integer, default=3)

    # Assignment (Feature 56)
    auto_assign_agents: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_agent_ids: Mapped[list[UUIDType] | None] = mapped_column(JSONB, default=list)
    required_skills: Mapped[list[UUIDType] | None] = mapped_column(JSONB, default=list)

    # Routing (Feature 57)
    routing_rules: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=dict
    )  # {conditions: [], targets: []}

    # Metadata
    category: Mapped[str | None] = mapped_column(String(100))
    tags: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Ownership
    created_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    owner_team_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agent_teams.id"), nullable=True
    )

    # Usage Stats
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_execution_time_ms: Mapped[int | None] = mapped_column(Integer)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    triggers: Mapped[list["WorkflowTrigger"]] = relationship(
        "WorkflowTrigger", back_populates="workflow", cascade="all, delete-orphan"
    )
    executions: Mapped[list["WorkflowExecution"]] = relationship(
        "WorkflowExecution", back_populates="workflow"
    )
    schedules: Mapped[list["WorkflowSchedule"]] = relationship(
        "WorkflowSchedule", back_populates="workflow", cascade="all, delete-orphan"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# WORKFLOW EXECUTION — Execution tracking (Feature 59)
# ═══════════════════════════════════════════════════════════════════════════════


class ExecutionStatus(StrEnum):
    """Workflow execution status."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class WorkflowExecution(Base):
    """
    Workflow Execution Instance

    Tracks each workflow run with full state.
    Feature 59: Skill Workflows
    """

    __tablename__ = "workflow_executions"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    execution_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    workflow_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("workflows.id"), nullable=False, index=True
    )

    # Trigger Info
    trigger_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # manual, scheduled, event, api
    trigger_source: Mapped[str | None] = mapped_column(String(255))

    # Input Data
    input_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Status
    status: Mapped[str] = mapped_column(String(50), default=ExecutionStatus.PENDING, index=True)
    status_message: Mapped[str | None] = mapped_column(Text)

    # Current Position
    current_node_id: Mapped[str | None] = mapped_column(String(255))
    completed_nodes: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    pending_nodes: Mapped[list[str] | None] = mapped_column(JSONB, default=list)

    # Results
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    results_summary: Mapped[str | None] = mapped_column(Text)

    # Performance
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    # Resource Usage
    cpu_time_ms: Mapped[int | None] = mapped_column(Integer)
    memory_peak_mb: Mapped[int | None] = mapped_column(Integer)

    # Error Handling (Feature 64, 65)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    retry_attempts: Mapped[int] = mapped_column(Integer, default=0)
    fallback_triggered: Mapped[bool] = mapped_column(Boolean, default=False)

    # Context
    execution_context: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=dict
    )  # Variables, state, etc.

    # Agents Involved (Feature 40)
    assigned_agent_ids: Mapped[list[UUIDType] | None] = mapped_column(JSONB, default=list)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    workflow: Mapped[Workflow] = relationship("Workflow", back_populates="executions")
    node_executions: Mapped[list["WorkflowNodeExecution"]] = relationship(
        "WorkflowNodeExecution", back_populates="execution", cascade="all, delete-orphan"
    )
    events: Mapped[list["WorkflowEvent"]] = relationship(
        "WorkflowEvent", back_populates="execution", cascade="all, delete-orphan"
    )


class WorkflowNodeExecution(Base):
    """Individual node execution within a workflow."""

    __tablename__ = "workflow_node_executions"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    execution_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("workflow_executions.id"), nullable=False
    )

    # Node Info
    node_id: Mapped[str] = mapped_column(String(255), nullable=False)
    node_type: Mapped[str] = mapped_column(String(100), nullable=False)
    node_name: Mapped[str | None] = mapped_column(String(255))

    # Skill Assignment
    assigned_skill_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=True
    )
    assigned_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    # Status
    status: Mapped[str] = mapped_column(String(50), default=ExecutionStatus.PENDING)

    # I/O
    input_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Performance
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    # Error
    error_message: Mapped[str | None] = mapped_column(Text)
    error_stacktrace: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Relationships
    execution: Mapped[WorkflowExecution] = relationship(
        "WorkflowExecution", back_populates="node_executions"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# WORKFLOW TRIGGER — Event triggers (Features 58, 66-70)
# ═══════════════════════════════════════════════════════════════════════════════


class TriggerType(StrEnum):
    """Types of workflow triggers."""

    EVENT = "event"  # System event
    WEBHOOK = "webhook"  # External webhook
    SCHEDULE = "schedule"  # Time-based
    API = "api"  # API call
    SKILL_USED = "skill_used"  # When skill is used
    AGENT_ACTION = "agent_action"
    DATA_CHANGE = "data_change"
    MANUAL = "manual"


class WorkflowTrigger(Base):
    """
    Workflow Event Trigger

    Features:
    - 58: Skill Triggers
    - 66: Auto-Discovery
    - 69: Skill Webhooks
    - 70: Event Streaming
    """

    __tablename__ = "workflow_triggers"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("workflows.id"), nullable=False
    )

    # Trigger Configuration
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    trigger_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Event Matching
    event_pattern: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=dict
    )  # {event_type, conditions: []}

    # Conditions (Feature 61)
    conditions: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, default=list
    )  # [{field, operator, value}]
    condition_logic: Mapped[str] = mapped_column(String(10), default="AND")  # AND, OR

    # Webhook Config (Feature 69)
    webhook_url: Mapped[str | None] = mapped_column(String(500))
    webhook_method: Mapped[str] = mapped_column(String(10), default="POST")
    webhook_headers: Mapped[dict[str, str] | None] = mapped_column(JSONB, default=dict)
    webhook_secret: Mapped[str | None] = mapped_column(String(255))

    # Input Mapping
    input_mapping: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=dict
    )  # {source_field: workflow_input}

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trigger_count: Mapped[int] = mapped_column(Integer, default=0)

    # Rate Limiting
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer)

    # Metadata
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    workflow: Mapped[Workflow] = relationship("Workflow", back_populates="triggers")


# ═══════════════════════════════════════════════════════════════════════════════
# WORKFLOW SCHEDULE — Scheduled execution (Feature 60)
# ═══════════════════════════════════════════════════════════════════════════════


class WorkflowSchedule(Base):
    """
    Scheduled Workflow Execution

    Feature 60: Scheduled Skill Execution
    """

    __tablename__ = "workflow_schedules"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("workflows.id"), nullable=False
    )

    # Schedule Configuration
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Cron Expression or Schedule
    cron_expression: Mapped[str | None] = mapped_column(String(100))
    interval_seconds: Mapped[int | None] = mapped_column(Integer)

    # Fixed Time
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    # Recurrence
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_runs: Mapped[int | None] = mapped_column(Integer)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    # Input Data for Scheduled Run
    default_input: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    workflow: Mapped[Workflow] = relationship("Workflow", back_populates="schedules")


# ═══════════════════════════════════════════════════════════════════════════════
# WORKFLOW EVENT — Event streaming (Feature 70)
# ═══════════════════════════════════════════════════════════════════════════════


class WorkflowEvent(Base):
    """
    Workflow Event for Streaming

    Feature 70: Skill Event Streaming
    """

    __tablename__ = "workflow_events"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    execution_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("workflow_executions.id"), nullable=False, index=True
    )

    # Event Details
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # started, node_completed, failed, completed
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)

    # Node Reference
    node_id: Mapped[str | None] = mapped_column(String(255))
    node_name: Mapped[str | None] = mapped_column(String(255))

    # Event Data
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Severity
    severity: Mapped[str] = mapped_column(
        String(20), default="info"
    )  # debug, info, warning, error, critical

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    # Relationships
    execution: Mapped[WorkflowExecution] = relationship(
        "WorkflowExecution", back_populates="events"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE — Pipeline builder (Features 62, 63)
# ═══════════════════════════════════════════════════════════════════════════════


class Pipeline(Base):
    """
    Pipeline Definition

    Features:
    - 62: Pipeline Builder
    - 63: Batch Processing
    """

    __tablename__ = "pipelines"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    pipeline_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Pipeline Type
    pipeline_type: Mapped[str] = mapped_column(
        String(50), default="linear"
    )  # linear, branching, fan-out, fan-in

    # Nodes (DAG Definition)
    nodes: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, default=list
    )  # [{id, type, config, dependencies: []}]

    # Batch Processing (Feature 63)
    batch_size: Mapped[int] = mapped_column(Integer, default=1)
    max_concurrent_batches: Mapped[int] = mapped_column(Integer, default=5)

    # Settings
    is_parallel: Mapped[bool] = mapped_column(Boolean, default=False)
    error_handling: Mapped[str] = mapped_column(String(50), default="stop")  # stop, continue, retry

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Metadata
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    runs: Mapped[list["PipelineRun"]] = relationship("PipelineRun", back_populates="pipeline")


class PipelineRun(Base):
    """Pipeline execution run."""

    __tablename__ = "pipeline_runs"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    pipeline_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("pipelines.id"), nullable=False
    )

    # Status
    status: Mapped[str] = mapped_column(String(50), default=ExecutionStatus.PENDING)

    # Batch Info (Feature 63)
    batch_index: Mapped[int] = mapped_column(Integer, default=0)
    total_batches: Mapped[int] = mapped_column(Integer, default=1)

    # Input/Output
    input_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Performance
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    # Node Results
    node_results: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=dict
    )  # {node_id: {status, output, duration}}

    # Error
    error_message: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    pipeline: Mapped[Pipeline] = relationship("Pipeline", back_populates="runs")
