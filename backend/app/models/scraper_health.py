import uuid
from sqlalchemy import (
    UUID, Boolean, Column, DateTime, Integer,
    Numeric, String, Text, func,
)
from .base import Base


class ScraperHealth(Base):
    __tablename__ = "scraper_health"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_name = Column(String(100), unique=True, nullable=False)
    last_attempted_at = Column(DateTime(timezone=True))
    last_success_at = Column(DateTime(timezone=True))
    consecutive_failures = Column(Integer, default=0)
    total_runs = Column(Integer, default=0)
    total_successes = Column(Integer, default=0)
    success_rate = Column(Numeric(5, 2))
    is_muted = Column(Boolean, default=False)
    muted_until = Column(DateTime(timezone=True))
    last_error = Column(Text)
    avg_items_per_run = Column(Numeric(8, 2))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
