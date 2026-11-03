"""Tenant-scoped organic content batch orchestration records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TenantMixin


class ContentBatch(Base, TenantMixin):
    """One queued, approval-aware organic content composition."""

    __tablename__ = "content_batches"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_content_batches_org_idempotency",
        ),
        Index("ix_content_batches_org_status", "organization_id", "status"),
        CheckConstraint(
            "status IN ('queued','processing','exported','published','blocked','failed')",
            name="ck_content_batch_status",
        ),
        CheckConstraint("site IN ('site_a','site_b')", name="ck_content_batch_site"),
        CheckConstraint("language IN ('en','th')", name="ck_content_batch_language"),
        CheckConstraint(
            "item_count >= 0 AND item_count <= 9",
            name="ck_content_batch_item_count",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    site: Mapped[str] = mapped_column(String(20), nullable=False, default="site_a")
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="organic")

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=9, server_default="9")
    live: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    fallback_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    approval_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="SET NULL")
    )
    claim_reviewed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    claim_ids: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    canary_passed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    provider_consent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    provider_credentials_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    utm_source: Mapped[str | None] = mapped_column(String(100))
    utm_medium: Mapped[str | None] = mapped_column(String(100))
    utm_campaign: Mapped[str | None] = mapped_column(String(255))
    block_codes: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    export_manifest: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["ContentBatchItem"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ContentBatchItem.position",
        lazy="selectin",
    )


class ContentBatchItem(Base):
    """One idempotent pillar, supporting page, or short-form adaptation."""

    __tablename__ = "content_batch_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "item_key", name="uq_content_batch_items_key"),
        UniqueConstraint(
            "batch_id",
            "idempotency_key",
            name="uq_content_batch_items_idempotency",
        ),
        Index("ix_content_batch_items_batch_status", "batch_id", "status"),
        CheckConstraint(
            "role IN ('pillar','supporting','short')",
            name="ck_content_batch_item_role",
        ),
        CheckConstraint(
            "status IN ('draft','dry_run','blocked','published','failed')",
            name="ck_content_batch_item_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_key: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    utm_params: Mapped[dict[str, str] | None] = mapped_column(JSONB, default=dict)
    claim_ids: Mapped[list[str] | None] = mapped_column(JSONB, default=list)

    article_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("content_articles.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    fallback_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    provider_status: Mapped[str | None] = mapped_column(String(64))
    publish_receipt: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    block_codes: Mapped[list[str] | None] = mapped_column(JSONB, default=list)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    batch: Mapped[ContentBatch] = relationship(back_populates="items")
