import uuid
from sqlalchemy import (
    UUID, Boolean, CheckConstraint, Column, DateTime, ForeignKey,
    Integer, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base


class ContentDraft(Base):
    __tablename__ = "content_drafts"
    __table_args__ = (
        CheckConstraint(
            "type IN ('proposal','linkedin_post','outreach_dm','follow_up','application_essay','cv_update','bio_update','other')",
            name="ck_draft_type",
        ),
        CheckConstraint(
            "status IN ('pending','approved','rejected','sent','revised')",
            name="ck_draft_status",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String(50))
    title = Column(String(500))
    content = Column(Text, nullable=False)
    context_notes = Column(Text)
    review_notes = Column(Text)
    status = Column(String(30), default="pending")
    approved_at = Column(DateTime(timezone=True))
    rejection_reason = Column(Text)
    revision_request = Column(Text)
    opportunity_id = Column(UUID(as_uuid=True), ForeignKey("opportunities.id"))
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"))
    submission_id = Column(UUID(as_uuid=True), ForeignKey("submissions.id"))
    model_used = Column(String(100))
    generation_tokens = Column(Integer)
    generation_cost_usd = Column(Numeric(8, 6))
    used_playbook_ids = Column(JSONB, default=list)
    was_fallback_draft = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
