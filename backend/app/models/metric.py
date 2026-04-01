import uuid
from sqlalchemy import (
    UUID, Column, Date, DateTime, Integer,
    Numeric, String, Text, func,
)
from .base import Base


class WeeklyMetric(Base):
    __tablename__ = "weekly_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    week_start = Column(Date, unique=True, nullable=False)
    opps_found = Column(Integer, default=0)
    opps_scored = Column(Integer, default=0)
    opps_decided = Column(Integer, default=0)
    opps_actioned = Column(Integer, default=0)
    opps_ignored = Column(Integer, default=0)
    outreach_sent = Column(Integer, default=0)
    outreach_replied = Column(Integer, default=0)
    reply_rate = Column(Numeric(5, 2))
    meetings_booked = Column(Integer, default=0)
    proposals_sent = Column(Integer, default=0)
    proposals_won = Column(Integer, default=0)
    close_rate = Column(Numeric(5, 2))
    revenue_thb = Column(Numeric(12, 2), default=0)
    pipeline_value_thb = Column(Numeric(12, 2), default=0)
    comps_found = Column(Integer, default=0)
    comps_applied = Column(Integer, default=0)
    comps_results = Column(Integer, default=0)
    ai_cost_usd = Column(Numeric(8, 4), default=0)
    tasks_completed = Column(Integer, default=0)
    tasks_failed = Column(Integer, default=0)
    scraper_success_rate = Column(Numeric(5, 2))
    decision_accuracy_score = Column(Numeric(5, 2))
    avg_energy_this_week = Column(Numeric(4, 2))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
