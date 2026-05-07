"""
Usage tracking for billing metering.
Log every chargeable action here.
Features: lead_discovery | draft_generation | email_send | ai_scoring
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

# Forward reference type checking
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.organization import Organization

VALID_FEATURES = [
    "lead_discovery", "draft_generation", "email_send", "ai_scoring", "api_call",
    "ai_request", "skill_execution", "skill_error", "agent_execution"
]


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    feature: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # AI usage tracking fields
    model_name: Mapped[str | None] = mapped_column(String(100), index=True)  # gpt-4, claude-sonnet, etc.
    tokens_input: Mapped[int | None] = mapped_column(Integer)
    tokens_output: Mapped[int | None] = mapped_column(Integer)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))

    # Legacy field for backward compatibility
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    organization: Mapped["Organization"] = relationship("Organization", back_populates="usage_logs")
