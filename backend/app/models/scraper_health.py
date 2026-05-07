import uuid
from datetime import datetime
from decimal import Decimal
from uuid import UUID as UUIDType

from sqlalchemy import UUID as SQLUUID
from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ScraperHealth(Base):
    __tablename__ = "scraper_health"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int | None] = mapped_column(Integer, default=0)
    total_runs: Mapped[int | None] = mapped_column(Integer, default=0)
    total_successes: Mapped[int | None] = mapped_column(Integer, default=0)
    success_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    is_muted: Mapped[bool | None] = mapped_column(Boolean, default=False)
    muted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    avg_items_per_run: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
