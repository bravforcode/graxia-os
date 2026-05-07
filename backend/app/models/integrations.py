"""
Third-Party Integrations — Features 71-80
External service integrations and connectors
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
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as SQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 71-75: INTEGRATION CONNECTORS
# ═══════════════════════════════════════════════════════════════════════════════


class IntegrationProvider(Base):
    """Available integration providers."""

    __tablename__ = "integration_providers"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    provider_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Provider type
    provider_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # llm, database, storage, messaging, etc.
    category: Mapped[str] = mapped_column(String(50), index=True)  # ai, cloud, communication

    # Capabilities
    supported_features: Mapped[list[str]] = mapped_column(JSONB, default=list)
    required_credentials: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # Configuration schema
    config_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict
    )  # JSON Schema for config validation

    # Documentation
    documentation_url: Mapped[str | None] = mapped_column(String(500))
    icon_url: Mapped[str | None] = mapped_column(String(500))

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)

    popularity_score: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class IntegrationConnection(Base):
    """Active connections to external services."""

    __tablename__ = "integration_connections"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    connection_key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )

    provider_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("integration_providers.id"), nullable=False, index=True
    )

    # Owner
    agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True, index=True
    )
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)

    # Connection name
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Encrypted credentials (store reference, actual in secure vault)
    credentials_ref: Mapped[str | None] = mapped_column(String(255))  # Reference to secret manager

    # Configuration
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, connected, error, disabled
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health_status: Mapped[str | None] = mapped_column(String(20))  # healthy, degraded, failed

    # Usage
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Error tracking
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class IntegrationWebhook(Base):
    """Webhook configurations for integrations."""

    __tablename__ = "integration_webhooks"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    webhook_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    connection_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("integration_connections.id"), nullable=False, index=True
    )

    # Webhook configuration
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Endpoint
    endpoint_url: Mapped[str] = mapped_column(String(500), nullable=False)
    http_method: Mapped[str] = mapped_column(String(10), default="POST")
    headers: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)

    # Payload
    payload_template: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Security
    secret_token: Mapped[str | None] = mapped_column(String(255))
    signature_header: Mapped[str | None] = mapped_column(String(100))

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Stats
    total_deliveries: Mapped[int] = mapped_column(Integer, default=0)
    successful_deliveries: Mapped[int] = mapped_column(Integer, default=0)
    failed_deliveries: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 76-78: DATA SYNC & MIGRATION
# ═══════════════════════════════════════════════════════════════════════════════


class DataSyncJob(Base):
    """Data synchronization jobs between systems."""

    __tablename__ = "data_sync_jobs"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    job_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Source and destination
    source_connection_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("integration_connections.id"), nullable=False
    )
    destination_connection_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("integration_connections.id"), nullable=False
    )

    # Sync configuration
    source_query: Mapped[str | None] = mapped_column(Text)
    destination_mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    transform_rules: Mapped[list[dict]] = mapped_column(JSONB, default=list)

    # Schedule
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_cron: Mapped[str | None] = mapped_column(String(100))

    # Sync options
    sync_type: Mapped[str] = mapped_column(String(20), default="full")  # full, incremental
    conflict_resolution: Mapped[str] = mapped_column(
        String(20), default="skip"
    )  # skip, overwrite, merge

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Stats
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_status: Mapped[str | None] = mapped_column(String(20))
    total_runs: Mapped[int] = mapped_column(Integer, default=0)

    created_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class DataSyncRun(Base):
    """Individual sync run execution records."""

    __tablename__ = "data_sync_runs"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    job_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("data_sync_jobs.id"), nullable=False, index=True
    )

    run_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # Execution details
    status: Mapped[str] = mapped_column(
        String(20), default="running"
    )  # running, completed, failed, cancelled

    # Records
    records_read: Mapped[int] = mapped_column(Integer, default=0)
    records_written: Mapped[int] = mapped_column(Integer, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)

    # Performance
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)

    # Error details
    error_message: Mapped[str | None] = mapped_column(Text)
    error_details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 79-80: API GATEWAY & EVENTS
# ═══════════════════════════════════════════════════════════════════════════════


class ExternalApiCall(Base):
    """Log of external API calls."""

    __tablename__ = "external_api_calls"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    connection_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("integration_connections.id"), nullable=True, index=True
    )

    # Request details
    api_endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    http_method: Mapped[str] = mapped_column(String(10), nullable=False)
    request_headers: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    request_body: Mapped[str | None] = mapped_column(Text)

    # Response details
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_headers: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    response_body: Mapped[str | None] = mapped_column(Text)

    # Performance
    request_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    # Error
    error_occurred: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    # Caller context
    triggered_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    triggered_by_skill_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class IntegrationEvent(Base):
    """Events from external integrations."""

    __tablename__ = "integration_events"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    event_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    connection_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("integration_connections.id"), nullable=False, index=True
    )

    # Event details
    provider_event_id: Mapped[str | None] = mapped_column(String(255), index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_subtype: Mapped[str | None] = mapped_column(String(100))

    # Payload
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Processing
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_result: Mapped[str | None] = mapped_column(Text)

    # Actions taken
    actions_triggered: Mapped[list[dict]] = mapped_column(JSONB, default=list)

    # Retry
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
