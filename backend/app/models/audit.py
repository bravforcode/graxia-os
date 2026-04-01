import uuid
from sqlalchemy import (
    UUID, Boolean, Column, DateTime, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action = Column(String(200), nullable=False)
    entity_type = Column(String(100))
    entity_id = Column(UUID(as_uuid=True))
    details = Column(JSONB, default=dict)
    triggered_by = Column(String(100))
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    ai_model_used = Column(String(100))
    was_fallback = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
