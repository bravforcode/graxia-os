import uuid
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID as UUIDType

from sqlalchemy import (
    UUID as SQLUUID,
)
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class JobPosting(Base, TenantMixin):
    __tablename__ = "job_postings"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('job','freelance')",
            name="ck_job_posting_type",
        ),
        CheckConstraint(
            "status IN ('discovered','screened','drafted','approved','applied','interview_scheduled','interviewing','offer_received','negotiating','accepted','rejected','archived')",
            name="ck_job_posting_status",
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255))
    source_platform: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(255))
    job_type: Mapped[str] = mapped_column(String(30), nullable=False)
    employment_type: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    required_skills: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    matched_skills: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    skill_gap_list: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    tags: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    fit_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(30), default="discovered")
    follow_up_due: Mapped[date | None] = mapped_column(Date)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opportunity_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("opportunities.id")
    )
    source_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    raw_data: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
