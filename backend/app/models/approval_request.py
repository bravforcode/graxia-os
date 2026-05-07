import uuid
from datetime import datetime
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import UUID as SQLUUID
from sqlalchemy import CheckConstraint, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','expired','cancelled')",
            name="ck_approval_status",
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_type: Mapped[str | None] = mapped_column(String(100))
    subject_id: Mapped[UUIDType | None] = mapped_column(SQLUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    policy_class: Mapped[str] = mapped_column(String(50), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(100))
    batch_key: Mapped[str | None] = mapped_column(String(200))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    preview: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
