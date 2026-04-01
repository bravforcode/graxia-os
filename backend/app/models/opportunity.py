import uuid
from datetime import date, datetime
from sqlalchemy import (
    UUID, Boolean, CheckConstraint, Column, Date, DateTime,
    Integer, Numeric, SmallInteger, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
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
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    source_url = Column(Text)
    source_platform = Column(String(100))
    deadline = Column(Date)
    application_open = Column(Date)

    money_score = Column(SmallInteger)
    brand_score = Column(SmallInteger)
    network_score = Column(SmallInteger)
    startup_score = Column(SmallInteger)
    effort_score = Column(SmallInteger)
    total_score = Column(Numeric(4, 2))
    scoring_rationale = Column(Text)
    red_flags = Column(JSONB, default=list)

    decision = Column(String(20))
    decision_confidence = Column(Numeric(3, 2))
    decision_reasoning = Column(Text)
    decision_factors = Column(JSONB, default=dict)
    review_after = Column(Date)

    conviction_score = Column(SmallInteger)
    user_notes = Column(Text)
    status = Column(String(50), default="found")

    prize_amount = Column(String(300))
    prize_currency = Column(String(10))
    requirements = Column(JSONB, default=list)
    tags = Column(JSONB, default=list)
    is_team_allowed = Column(Boolean)
    max_team_size = Column(Integer)
    is_student_eligible = Column(Boolean)
    location_type = Column(String(30))
    fit_summary = Column(Text)
    action_priority = Column(String(20))
    raw_data = Column(JSONB, default=dict)

    found_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    acted_on_at = Column(DateTime(timezone=True))
    source_hash = Column(String(64), unique=True)
