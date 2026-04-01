import uuid
from datetime import datetime
from sqlalchemy import (
    UUID, CheckConstraint, Column, DateTime, ForeignKey,
    SmallInteger, String, Text, UniqueConstraint, func,
)
from .base import Base


class ContactEdge(Base):
    __tablename__ = "contact_edges"
    __table_args__ = (
        CheckConstraint(
            "edge_type IN ('referred','worked_with','mentor_of','organizes','knows','invested_in','co_founded')",
            name="ck_edge_type",
        ),
        CheckConstraint("strength BETWEEN 1 AND 5", name="ck_edge_strength"),
        UniqueConstraint("from_contact_id", "to_contact_id", "edge_type", name="uq_edge"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"))
    to_contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"))
    edge_type = Column(String(50))
    strength = Column(SmallInteger, default=3)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
