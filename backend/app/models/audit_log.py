import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    """
    Enterprise Audit Log: Records every sensitive tool execution.
    Necessary for SOC2 and security compliance.
    """
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), 
        nullable=True, 
        index=True
    )
    
    action: Mapped[str] = mapped_column(String(255), nullable=False, index=True) # e.g. "shell_command", "read_file"
    details: Mapped[str | None] = mapped_column(Text, nullable=True) # e.g. the command or path
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    
    status: Mapped[str] = mapped_column(String(50), default="success") # "success", "failed", "blocked"
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
