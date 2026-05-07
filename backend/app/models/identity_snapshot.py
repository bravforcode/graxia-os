import uuid
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID as UUIDType

from sqlalchemy import UUID as SQLUUID
from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class IdentitySnapshot(Base):
    __tablename__ = "identity_snapshots"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    positioning_label: Mapped[str | None] = mapped_column(String(200))
    profile_hash: Mapped[str | None] = mapped_column(String(64))
    key_skills: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    primary_narrative: Mapped[str | None] = mapped_column(Text)
    revenue_at_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    competitions_won_at_snapshot: Mapped[int | None] = mapped_column(Integer)
    change_trigger: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
