import uuid
from sqlalchemy import (
    UUID, CheckConstraint, Column, DateTime, ForeignKey,
    Numeric, SmallInteger, String, Text, func,
)
from .base import Base


class OutcomePattern(Base):
    __tablename__ = "outcome_patterns"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('positive','negative','neutral')",
            name="ck_outcome",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id = Column(UUID(as_uuid=True), ForeignKey("opportunities.id"))
    submission_id = Column(UUID(as_uuid=True), ForeignKey("submissions.id"))
    opportunity_type = Column(String(50))
    client_type = Column(String(50))
    money_score = Column(SmallInteger)
    brand_score = Column(SmallInteger)
    network_score = Column(SmallInteger)
    startup_score = Column(SmallInteger)
    effort_score = Column(SmallInteger)
    total_score = Column(Numeric(4, 2))
    decision_at_time = Column(String(20))
    conviction_score_at_time = Column(SmallInteger)
    energy_at_time = Column(SmallInteger)
    outcome = Column(String(20))
    actual_value_thb = Column(Numeric(12, 2))
    lost_reason = Column(String(50))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
