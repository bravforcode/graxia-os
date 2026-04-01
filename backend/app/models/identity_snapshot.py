import uuid
from sqlalchemy import (
    UUID, Column, Date, DateTime, Integer,
    Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base


class IdentitySnapshot(Base):
    __tablename__ = "identity_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_date = Column(Date, nullable=False)
    positioning_label = Column(String(200))
    profile_hash = Column(String(64))
    key_skills = Column(JSONB, default=list)
    primary_narrative = Column(Text)
    revenue_at_snapshot = Column(Numeric(12, 2))
    competitions_won_at_snapshot = Column(Integer)
    change_trigger = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
