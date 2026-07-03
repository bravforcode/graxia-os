import uuid

from sqlalchemy import (
    UUID,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base, TenantMixin


class Contact(Base, TenantMixin):
    __tablename__ = "contacts"
    __table_args__ = (
        CheckConstraint(
            "contact_type IN ('client','lead','mentor','founder','investor','recruiter','collaborator','event_organizer','other')",
            name="ck_contact_type",
        ),
        CheckConstraint("relationship_strength BETWEEN 1 AND 5", name="ck_contact_rel_strength"),
        CheckConstraint("value_score BETWEEN 1 AND 10", name="ck_contact_value_score"),
        Index(
            "ix_contacts_company_deleted_created_at",
            "company",
            "is_deleted",
            "created_at",
        ),
        Index(
            "ix_contacts_email_deleted",
            "email",
            "is_deleted",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(300), nullable=False)
    role = Column(String(200))
    company = Column(String(300))
    contact_type = Column(String(50))
    status = Column(String(50), default="New")
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
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    interactions = relationship("NetworkInteraction", back_populates="contact", cascade="all, delete-orphan")
