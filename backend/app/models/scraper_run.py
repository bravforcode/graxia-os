"""Scraper run model for tracking scraper execution history."""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, Index, Integer, String, Text, case, func, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ScraperRun(Base):
    """
    Scraper run model for tracking scraper execution history.
    
    Attributes:
        id: Unique identifier
        scraper_name: Name of scraper
        platform: Platform being scraped
        run_type: Type of run (scheduled, manual, retry)
        items_found: Number of items found
        items_new: Number of new items
        items_updated: Number of updated items
        duration_seconds: Run duration in seconds
        status: Run status (success, partial, failed)
        error_message: Error message if failed
        started_at: When run started
        completed_at: When run completed
        created_at: Creation timestamp
    """
    
    __tablename__ = "scraper_runs"
    
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    scraper_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    platform: Mapped[str | None] = mapped_column(String(100))
    run_type: Mapped[str | None] = mapped_column(String(50))
    items_found: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    items_new: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    items_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(50), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_utc_now)
    
    __table_args__ = (
        Index("idx_scraper_started", "started_at", postgresql_ops={"started_at": "DESC"}),
    )
    
    def __repr__(self) -> str:
        return f"<ScraperRun(id={self.id}, scraper='{self.scraper_name}', status='{self.status}')>"
    
    @property
    def is_success(self) -> bool:
        """Check if run was successful."""
        return self.status == "success"
    
    @property
    def is_failed(self) -> bool:
        """Check if run failed."""
        return self.status == "failed"
    
    @property
    def is_partial(self) -> bool:
        """Check if run was partially successful."""
        return self.status == "partial"
    
    @property
    def success_rate(self) -> float | None:
        """Calculate success rate (new + updated / found)."""
        if not self.items_found:
            return None
        return (self.items_new + self.items_updated) / self.items_found
    
    def mark_started(self) -> None:
        """Mark run as started."""
        self.started_at = _utc_now()
        self.status = "running"
    
    def mark_completed(self, status: str = "success") -> None:
        """Mark run as completed."""
        self.completed_at = _utc_now()
        self.status = status
        if self.started_at:
            self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
    
    def mark_failed(self, error_message: str) -> None:
        """Mark run as failed."""
        self.completed_at = _utc_now()
        self.status = "failed"
        self.error_message = error_message
        if self.started_at:
            self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
    
    @classmethod
    async def get_recent_runs(cls, session, scraper_name: str, limit: int = 10):
        """Get recent runs for a scraper."""
        result = await session.execute(
            select(cls)
            .where(cls.scraper_name == scraper_name)
            .order_by(cls.started_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    @classmethod
    async def get_success_rate(cls, session, scraper_name: str, days: int = 7) -> float:
        """Get success rate for a scraper over last N days."""
        cutoff = _utc_now() - timedelta(days=days)
        
        result = await session.execute(
            select(
                func.count(cls.id).label("total"),
                func.count(case((cls.status == "success", 1))).label("success")
            )
            .where(cls.scraper_name == scraper_name)
            .where(cls.started_at >= cutoff)
        )
        
        row = result.first()
        if not row or not row.total:
            return 0.0
        return row.success / row.total
