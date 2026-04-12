import uuid
from datetime import datetime
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import UUID as SQLUUID, Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUIDType] = mapped_column(SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[UUIDType] = mapped_column(SQLUUID(as_uuid=True), default=uuid.uuid4, nullable=False)
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, default="legacy.audit")
    event_category: Mapped[str] = mapped_column(String(50), nullable=False, default="system")
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="INFO")
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[UUIDType | None] = mapped_column(SQLUUID(as_uuid=True))
    user_id: Mapped[UUIDType | None] = mapped_column(SQLUUID(as_uuid=True))
    session_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    request_path: Mapped[str | None] = mapped_column(String(500))
    request_method: Mapped[str | None] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, default=dict)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    triggered_by: Mapped[str | None] = mapped_column(String(100))
    success: Mapped[bool | None] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    ai_model_used: Mapped[str | None] = mapped_column(String(100))
    was_fallback: Mapped[bool | None] = mapped_column(Boolean, default=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
