import uuid
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID as UUIDType

from sqlalchemy import UUID as SQLUUID, Date, DateTime, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class WeeklyMetric(Base):
    __tablename__ = "weekly_metrics"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    week_start: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    opps_found: Mapped[int | None] = mapped_column(Integer, default=0)
    opps_scored: Mapped[int | None] = mapped_column(Integer, default=0)
    opps_decided: Mapped[int | None] = mapped_column(Integer, default=0)
    opps_actioned: Mapped[int | None] = mapped_column(Integer, default=0)
    opps_ignored: Mapped[int | None] = mapped_column(Integer, default=0)
    outreach_sent: Mapped[int | None] = mapped_column(Integer, default=0)
    outreach_replied: Mapped[int | None] = mapped_column(Integer, default=0)
    reply_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    meetings_booked: Mapped[int | None] = mapped_column(Integer, default=0)
    proposals_sent: Mapped[int | None] = mapped_column(Integer, default=0)
    proposals_won: Mapped[int | None] = mapped_column(Integer, default=0)
    close_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    revenue_thb: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=0)
    pipeline_value_thb: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=0)
    comps_found: Mapped[int | None] = mapped_column(Integer, default=0)
    comps_applied: Mapped[int | None] = mapped_column(Integer, default=0)
    comps_results: Mapped[int | None] = mapped_column(Integer, default=0)
    ai_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), default=0)
    tasks_completed: Mapped[int | None] = mapped_column(Integer, default=0)
    tasks_failed: Mapped[int | None] = mapped_column(Integer, default=0)
    scraper_success_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    decision_accuracy_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    avg_energy_this_week: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
