"""OpenClaw usage model for cost tracking."""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OpenClawUsage(Base):
    """
    OpenClaw usage model for tracking API costs.
    
    Attributes:
        id: Unique identifier
        platform: Platform name (linkedin, upwork, fiverr, etc.)
        action: Action performed (scrape, extract_contacts, extract_jobs)
        cost_usd: Cost in USD
        created_at: Creation timestamp
    """
    
    __tablename__ = "openclaw_usage"
    
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    
    __table_args__ = (
        Index("idx_openclaw_platform", "platform"),
        Index("idx_openclaw_created", "created_at", postgresql_ops={"created_at": "DESC"}),
    )
    
    def __repr__(self) -> str:
        return f"<OpenClawUsage(id={self.id}, platform='{self.platform}', cost=${self.cost_usd})>"
