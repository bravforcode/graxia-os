"""Network interaction model for tracking contact interactions."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class NetworkInteraction(Base):
    """
    Network interaction model for tracking interactions with contacts.
    
    Attributes:
        id: Unique identifier
        contact_id: Foreign key to contacts
        interaction_type: Type of interaction (outreach, meeting, email, call, etc.)
        interaction_at: When interaction occurred
        notes: Interaction notes
        created_at: Creation timestamp
    """
    
    __tablename__ = "network_interactions"
    
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    contact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    interaction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    interaction_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    contact = relationship("Contact", back_populates="interactions")
    
    __table_args__ = (
        Index("idx_network_interaction_contact", "contact_id"),
        Index("idx_network_interaction_at", "interaction_at", postgresql_ops={"interaction_at": "DESC"}),
    )
    
    def __repr__(self) -> str:
        return f"<NetworkInteraction(id={self.id}, type='{self.interaction_type}', contact_id={self.contact_id})>"
