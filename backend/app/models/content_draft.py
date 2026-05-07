import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import (
    UUID as SQLUUID,
)
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

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

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    type: Mapped[str | None] = mapped_column(String(50))
    title: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context_notes: Mapped[str | None] = mapped_column(Text)
    review_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(30), default="pending")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    revision_request: Mapped[str | None] = mapped_column(Text)
    opportunity_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("opportunities.id")
    )
    contact_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("contacts.id")
    )
    submission_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("submissions.id")
    )
    model_used: Mapped[str | None] = mapped_column(String(100))
    generation_tokens: Mapped[int | None] = mapped_column(Integer)
    generation_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    used_playbook_ids: Mapped[list[Any] | None] = mapped_column(JSONB, default=list)
    was_fallback_draft: Mapped[bool | None] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
