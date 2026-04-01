import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    UUID, CheckConstraint, Column, Date, DateTime, ForeignKey,
    Numeric, SmallInteger, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base


class Submission(Base):
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
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id = Column(UUID(as_uuid=True), ForeignKey("opportunities.id"))
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"))
    type = Column(String(50))
    title = Column(String(500))
    status = Column(String(50), default="draft")
    content = Column(Text)
    subject_line = Column(String(500))
    attachments = Column(JSONB, default=list)
    sent_at = Column(DateTime(timezone=True))
    opened_at = Column(DateTime(timezone=True))
    replied_at = Column(DateTime(timezone=True))
    follow_up_date = Column(Date)
    outcome_at = Column(DateTime(timezone=True))
    outcome_notes = Column(Text)
    proposed_value = Column(Numeric(12, 2))
    currency = Column(String(10), default="THB")
    actual_value = Column(Numeric(12, 2))
    lost_reason_primary = Column(String(50))
    lost_reason_secondary = Column(String(50))
    lost_stage = Column(String(30))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
