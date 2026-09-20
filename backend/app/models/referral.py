from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import (
    UUID as SQLUUID,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class ReferralPartner(Base, TenantMixin):
    """An organization-scoped partner that an operator has approved."""

    __tablename__ = "referral_partners"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'suspended')",
            name="ck_referral_partner_status",
        ),
        CheckConstraint(
            "commission_rate >= 0 AND commission_rate <= 1",
            name="ck_referral_partner_commission_rate",
        ),
        Index("ix_referral_partners_org_status", "organization_id", "status"),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("0.20"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ReferralCode(Base, TenantMixin):
    """A non-guessable referral token whose raw value is never persisted."""

    __tablename__ = "referral_codes"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('captured_lead', 'verified_delivery', 'approved_partner')",
            name="ck_referral_code_source_type",
        ),
        CheckConstraint(
            "audience IN ('regular_user', 'partner')",
            name="ck_referral_code_audience",
        ),
        CheckConstraint(
            "commission_rate >= 0 AND commission_rate <= 1",
            name="ck_referral_code_commission_rate",
        ),
        UniqueConstraint("code_hash", name="uq_referral_codes_code_hash"),
        Index("ix_referral_codes_org_active", "organization_id", "is_active"),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[UUIDType] = mapped_column(SQLUUID(as_uuid=True), nullable=False)
    issuer_user_id: Mapped[UUIDType | None] = mapped_column(SQLUUID(as_uuid=True))
    owner_identity_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    partner_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("referral_partners.id", ondelete="SET NULL"), index=True
    )
    audience: Mapped[str] = mapped_column(String(30), nullable=False)
    redirect_path: Mapped[str] = mapped_column(String(500), nullable=False)
    bonus_asset_path: Mapped[str | None] = mapped_column(String(500))
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("0.00"), nullable=False
    )
    hold_days: Mapped[int] = mapped_column(Integer, default=14, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReferralAttribution(Base, TenantMixin):
    """The first valid referral recorded for a browser/session identifier."""

    __tablename__ = "referral_attributions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "session_id", name="uq_referral_attribution_org_session"
        ),
        Index("ix_referral_attributions_code", "referral_code_id"),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    referral_code_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("referral_codes.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    identity_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReferralConversion(Base, TenantMixin):
    """Server-verified, one-time reward/commission ledger entry."""

    __tablename__ = "referral_conversions"
    __table_args__ = (
        CheckConstraint(
            "reward_type IN ('regular_bonus', 'partner_commission')",
            name="ck_referral_conversion_reward_type",
        ),
        CheckConstraint(
            "settlement_status IN ('not_applicable', 'manual_pending', 'manual_settled', 'reversed')",
            name="ck_referral_conversion_settlement_status",
        ),
        UniqueConstraint("referral_code_id", name="uq_referral_conversion_code"),
        UniqueConstraint(
            "organization_id", "conversion_key", name="uq_referral_conversion_key"
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    referral_code_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("referral_codes.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    conversion_key: Mapped[str] = mapped_column(String(255), nullable=False)
    verified_order_id: Mapped[UUIDType] = mapped_column(SQLUUID(as_uuid=True), nullable=False)
    reward_type: Mapped[str] = mapped_column(String(30), nullable=False)
    bonus_asset_path: Mapped[str | None] = mapped_column(String(500))
    gross_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("0.00"), nullable=False
    )
    commission_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    hold_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="eligible", nullable=False)
    settlement_status: Mapped[str] = mapped_column(
        String(30), default="not_applicable", nullable=False
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
