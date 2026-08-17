"""PDPA compliance models — consent records and breach notifications.

Supplements the existing ComplianceAuditLog (tamper-evident audit trail in
app/core/compliance_audit.py) with the user-facing data subjects PDPA requires:
  - explicit consent per purpose (Sections 19, 23 PDPA)
  - breach notification tracking (72-hour notice, Section 37 PDPA)
"""
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class PrivacyConsent(Base, TenantMixin):
    """Record of a data subject's consent for a specific processing purpose."""

    __tablename__ = "privacy_consents"
    __table_args__ = (
        # One active consent per (user, purpose). Revoking writes granted=False
        # on the same row (keeps audit history), so the unique constraint is on
        # the pair, not on status.
        UniqueConstraint("user_id", "purpose", name="uq_privacy_consent_user_purpose"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)  # marketing, analytics, email
    granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="api", nullable=False)  # api, checkout, signup
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class BreachNotification(Base, TenantMixin):
    """PDPA breach record — tracked until the 72-hour regulator notice is sent."""

    __tablename__ = "breach_notifications"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    affected_subjects: Mapped[int] = mapped_column(default=0, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)  # low, medium, high, critical
    status: Mapped[str] = mapped_column(String(30), default="detected", nullable=False)  # detected, assessing, notified_regulator, resolved
    notified_regulator_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notification_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # detected_at + 72h
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
