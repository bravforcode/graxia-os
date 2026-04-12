import uuid
from datetime import datetime
from uuid import UUID as UUIDType

from sqlalchemy import UUID as SQLUUID, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DeployHistory(Base):
    __tablename__ = "deploy_history"

    id: Mapped[UUIDType] = mapped_column(SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    backend_digest: Mapped[str] = mapped_column(Text, nullable=False)
    frontend_digest: Mapped[str] = mapped_column(Text, nullable=False)
    operator: Mapped[str] = mapped_column(String(120), nullable=False)
    migration_version: Mapped[str | None] = mapped_column(String(100))
    smoke_test_result: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    rollback_limited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
