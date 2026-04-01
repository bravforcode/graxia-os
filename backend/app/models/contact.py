import uuid
from datetime import datetime
from sqlalchemy import (
    UUID, Boolean, CheckConstraint, Column, Date, DateTime,
    ForeignKey, SmallInteger, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        CheckConstraint(
            "contact_type IN ('client','lead','mentor','founder','investor','recruiter','collaborator','event_organizer','other')",
            name="ck_contact_type",
        ),
        CheckConstraint("relationship_strength BETWEEN 1 AND 5", name="ck_contact_rel_strength"),
        CheckConstraint("value_score BETWEEN 1 AND 10", name="ck_contact_value_score"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(300), nullable=False)
    role = Column(String(200))
    company = Column(String(300))
    contact_type = Column(String(50))
    linkedin_url = Column(Text)
    email = Column(String(300))
    telegram_handle = Column(String(200))
    github_handle = Column(String(200))
    other_channels = Column(JSONB, default=dict)
    relationship_strength = Column(SmallInteger, default=1)
    last_contacted_at = Column(Date)
    next_followup_date = Column(Date)
    followup_reason = Column(Text)
    notes = Column(Text)
    conversation_summary = Column(Text)
    met_at = Column(String(300))
    referred_by = Column(UUID(as_uuid=True), ForeignKey("contacts.id"))
    value_score = Column(SmallInteger)
    network_cluster = Column(String(100))
    is_bridge_node = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
