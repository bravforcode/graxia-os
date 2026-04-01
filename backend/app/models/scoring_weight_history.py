import uuid
from sqlalchemy import (
    UUID, Boolean, CheckConstraint, Column, DateTime,
    Integer, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base


class ScoringWeightHistory(Base):
    __tablename__ = "scoring_weight_history"
    __table_args__ = (
        CheckConstraint(
            "changed_by IN ('user','learning_engine','rollback')",
            name="ck_weight_changed_by",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version = Column(Integer, nullable=False)
    weights = Column(JSONB, nullable=False)
    previous_weights = Column(JSONB)
    changed_by = Column(String(50))
    change_reason = Column(Text)
    confidence_at_change = Column(Numeric(3, 2))
    data_points_analyzed = Column(Integer)
    is_current = Column(Boolean, default=True)
    applied_at = Column(DateTime(timezone=True), server_default=func.now())
    rolled_back_at = Column(DateTime(timezone=True))
