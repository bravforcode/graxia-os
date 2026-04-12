import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import (
    UUID as SQLUUID,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint(
            "type IN ('freelance','competition','hackathon','grant','accelerator','fellowship','job','other')",
            name="ck_opp_type",
        ),
        CheckConstraint("money_score BETWEEN 0 AND 10", name="ck_opp_money_score"),
        CheckConstraint("brand_score BETWEEN 0 AND 10", name="ck_opp_brand_score"),
        CheckConstraint("network_score BETWEEN 0 AND 10", name="ck_opp_network_score"),
        CheckConstraint("startup_score BETWEEN 0 AND 10", name="ck_opp_startup_score"),
        CheckConstraint("effort_score BETWEEN 0 AND 10", name="ck_opp_effort_score"),
        CheckConstraint(
            "decision IN ('do_now','delay','skip','ask_user')",
            name="ck_opp_decision",
        ),
        CheckConstraint("conviction_score BETWEEN 1 AND 10", name="ck_opp_conviction"),
        CheckConstraint(
            "status IN ('found','scored','decided','reviewed','approved','in_progress','applied','waiting','accepted','rejected','withdrawn','ignored')",
            name="ck_opp_status",
        ),
        CheckConstraint(
            "location_type IN ('online','thailand','asean','global')",
            name="ck_opp_location_type",
        ),
        CheckConstraint(
            "action_priority IN ('do_now','queue','skip')",
            name="ck_opp_action_priority",
        ),
        Index(
            "ix_opportunities_status_deleted_found_at",
            "status",
            "is_deleted",
            "found_at",
        ),
        Index(
            "ix_opportunities_decision_deleted_score",
            "decision",
            "is_deleted",
            "total_score",
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_platform: Mapped[str | None] = mapped_column(String(100))
    deadline: Mapped[date | None] = mapped_column(Date)
    application_open: Mapped[date | None] = mapped_column(Date)

    money_score: Mapped[int | None] = mapped_column(SmallInteger)
    brand_score: Mapped[int | None] = mapped_column(SmallInteger)
    network_score: Mapped[int | None] = mapped_column(SmallInteger)
    startup_score: Mapped[int | None] = mapped_column(SmallInteger)
    effort_score: Mapped[int | None] = mapped_column(SmallInteger)
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    scoring_rationale: Mapped[str | None] = mapped_column(Text)
    red_flags: Mapped[list[Any] | None] = mapped_column(JSONB, default=list)

    decision: Mapped[str | None] = mapped_column(String(20))
    decision_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    decision_reasoning: Mapped[str | None] = mapped_column(Text)
    decision_factors: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    review_after: Mapped[date | None] = mapped_column(Date)

    conviction_score: Mapped[int | None] = mapped_column(SmallInteger)
    user_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(50), default="found")

    prize_amount: Mapped[str | None] = mapped_column(String(300))
    prize_currency: Mapped[str | None] = mapped_column(String(10))
    requirements: Mapped[list[Any] | None] = mapped_column(JSONB, default=list)
    tags: Mapped[list[Any] | None] = mapped_column(JSONB, default=list)
    is_team_allowed: Mapped[bool | None] = mapped_column(Boolean)
    max_team_size: Mapped[int | None] = mapped_column(Integer)
    is_student_eligible: Mapped[bool | None] = mapped_column(Boolean)
    location_type: Mapped[str | None] = mapped_column(String(30))
    fit_summary: Mapped[str | None] = mapped_column(Text)
    action_priority: Mapped[str | None] = mapped_column(String(20))
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    found_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    acted_on_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
