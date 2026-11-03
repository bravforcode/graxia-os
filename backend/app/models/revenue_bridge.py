from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    UUID as SQLUUID,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RevenueBridgeEvent(Base):
    """Verified provider evidence received by the Revenue OS bridge."""

    __tablename__ = "revenue_bridge_events"
    __table_args__ = (
        CheckConstraint(
            "event_kind IN ('subscription_activated', 'subscription_cancelled', 'payment_failed', 'refund')",
            name="ck_revenue_bridge_event_kind",
        ),
        CheckConstraint(
            "plan IN ('starter', 'growth', 'scale')",
            name="ck_revenue_bridge_plan",
        ),
        CheckConstraint("amount >= 0", name="ck_revenue_bridge_amount_non_negative"),
        CheckConstraint("currency = 'THB'", name="ck_revenue_bridge_currency_thb"),
        CheckConstraint(
            "normalized_status IN ('active', 'canceled', 'past_due', 'refunded')",
            name="ck_revenue_bridge_normalized_status",
        ),
        UniqueConstraint(
            "provider",
            "provider_event_id",
            name="uq_revenue_bridge_provider_event",
        ),
        Index(
            "ix_revenue_bridge_org_occurred",
            "organization_id",
            "occurred_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="THB")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    signature_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    normalized_status: Mapped[str] = mapped_column(String(20), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
