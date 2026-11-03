"""Mapping of migration 021; runtime never creates or migrates this table."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class DeliveryEmailEvent(Base, TenantMixin):
    __tablename__ = "delivery_email_events"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'sent', 'failed', 'skipped')", name="ck_delivery_email_status"),
        UniqueConstraint("idempotency_key", name="uq_delivery_email_idempotency"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("funnel_orders.id"), nullable=False, index=True)
    delivery_access_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("delivery_accesses.id"), index=True)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="pending")
    provider: Mapped[str] = mapped_column(String(100), nullable=False, server_default="mock")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message_redacted: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
