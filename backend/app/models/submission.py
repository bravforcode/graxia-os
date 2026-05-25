import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import (
    UUID as SQLUUID,
)
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class Submission(Base, TenantMixin):
    __tablename__ = "submissions"
    __table_args__ = (
        CheckConstraint(
            "type IN ('outreach_dm','application','proposal','follow_up','interview_prep')",
            name="ck_sub_type",
        ),
        CheckConstraint(
            "status IN ('draft','approved','sent','opened','replied','meeting_scheduled','negotiating','won','lost','withdrawn')",
            name="ck_sub_status",
        ),
        CheckConstraint(
            "lost_reason_primary IN ('no_reply','too_expensive','weak_fit','weak_message','timing_bad','stronger_competitor','deadline_missed','unclear_scope','student_status_disadvantage','other','unknown')",
            name="ck_sub_lost_reason",
        ),
        CheckConstraint(
            "lost_stage IN ('no_contact','initial_reply','proposal','negotiation','final_decision','unknown')",
            name="ck_sub_lost_stage",
        ),
        Index(
            "ix_submissions_status_deleted_created_at",
            "status",
            "is_deleted",
            "created_at",
        ),
        Index(
            "ix_submissions_opportunity_deleted_sent_at",
            "opportunity_id",
            "is_deleted",
            "sent_at",
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    opportunity_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("opportunities.id")
    )
    contact_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("contacts.id")
    )
    type: Mapped[str | None] = mapped_column(String(50))
    title: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str | None] = mapped_column(String(50), default="draft")
    content: Mapped[str | None] = mapped_column(Text)
    subject_line: Mapped[str | None] = mapped_column(String(500))
    attachments: Mapped[list[Any] | None] = mapped_column(JSONB, default=list)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    follow_up_date: Mapped[date | None] = mapped_column(Date)
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_notes: Mapped[str | None] = mapped_column(Text)
    proposed_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(10), default="THB")
    actual_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    lost_reason_primary: Mapped[str | None] = mapped_column(String(50))
    lost_reason_secondary: Mapped[str | None] = mapped_column(String(50))
    lost_stage: Mapped[str | None] = mapped_column(String(30))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
