"""
Organization — the billing and tenancy unit.
Every user belongs to an organization.
Every resource belongs to an organization.
"""

import uuid
from datetime import UTC, datetime

# Forward reference type checking
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.usage_log import UsageLog
    from app.models.user import User

# Single source of truth for plan limits
PLAN_LIMITS: dict[str, dict] = {
    "free": {"monthly_lead_limit": 10, "monthly_ai_credit_cents": 200, "seats": 1},
    "starter": {"monthly_lead_limit": 100, "monthly_ai_credit_cents": 1000, "seats": 1},
    "pro": {"monthly_lead_limit": 99999, "monthly_ai_credit_cents": 5000, "seats": 3},
}

VALID_PLANS = list(PLAN_LIMITS.keys())
VALID_STATUSES = ["active", "trialing", "past_due", "canceled", "suspended"]


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(f"plan IN ({','.join(repr(p) for p in VALID_PLANS)})", name="ck_org_plan"),
        CheckConstraint(
            f"status IN ({','.join(repr(s) for s in VALID_STATUSES)})", name="ck_org_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)

    # Stripe
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), index=True)

    # Plan
    plan: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Limits (synced from PLAN_LIMITS on plan change)
    monthly_lead_limit: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    monthly_ai_credit_cents: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    seats: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Privacy & Enterprise
    privacy_mode: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Metadata
    settings: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="organization")
    usage_logs: Mapped[list["UsageLog"]] = relationship(
        "UsageLog", back_populates="organization", cascade="all, delete-orphan"
    )

    @property
    def is_paid(self) -> bool:
        return self.plan in ("starter", "pro")

    @property
    def is_active(self) -> bool:
        return self.status in ("active", "trialing")

    @property
    def is_unlimited(self) -> bool:
        return self.plan == "pro"

    def apply_plan_limits(self) -> None:
        """Sync limits from PLAN_LIMITS after plan change."""
        limits = PLAN_LIMITS.get(self.plan, PLAN_LIMITS["free"])
        self.monthly_lead_limit = limits["monthly_lead_limit"]
        self.monthly_ai_credit_cents = limits["monthly_ai_credit_cents"]
        self.seats = limits["seats"]
