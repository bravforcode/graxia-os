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
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ScoringWeightHistory(Base):
    __tablename__ = "scoring_weight_history"
    __table_args__ = (
        CheckConstraint(
            "changed_by IN ('user','learning_engine','rollback')",
            name="ck_weight_changed_by",
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    previous_weights: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    changed_by: Mapped[str | None] = mapped_column(String(50))
    change_reason: Mapped[str | None] = mapped_column(Text)
    confidence_at_change: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    data_points_analyzed: Mapped[int | None] = mapped_column(Integer)
    is_current: Mapped[bool | None] = mapped_column(Boolean, default=True)
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
