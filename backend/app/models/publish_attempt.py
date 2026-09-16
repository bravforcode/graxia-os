"""Durable, redacted idempotency records for Content Ops publishing."""

from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PublishAttempt(Base):
    """One tenant/provider publish intent and its redacted terminal receipt.

    Raw provider payloads, tokens, and exception text intentionally have no
    column in this model. The unique key makes provider retries idempotent.
    """

    __tablename__ = "content_publish_attempts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "idempotency_key",
            name="uq_content_publish_attempts_idempotency",
        ),
        Index("ix_content_publish_attempts_tenant_status", "tenant_id", "provider_status"),
        CheckConstraint("length(trim(tenant_id)) > 0", name="ck_publish_attempt_tenant_nonempty"),
        CheckConstraint("length(trim(provider)) > 0", name="ck_publish_attempt_provider_nonempty"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(256), nullable=False)
    content_id: Mapped[str] = mapped_column(String(256), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    approval_id: Mapped[str] = mapped_column(String(256), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    live: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    provider_status: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(256))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    redacted_error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
