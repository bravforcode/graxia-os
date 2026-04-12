"""Email message model for individual emails within threads."""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Boolean, Text, TIMESTAMP, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class EmailMessage(Base):
    """
    Email message model for individual emails.
    
    Attributes:
        id: Unique identifier
        thread_id: Foreign key to email_threads
        message_id: Gmail message ID
        from_email: Sender email address
        to_email: Recipient email address
        subject: Email subject
        body: Email body text
        received_at: When email was received
        is_read: Whether message has been read
        created_at: Creation timestamp
    """
    
    __tablename__ = "email_messages"
    
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    thread_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("email_threads.id", ondelete="CASCADE"), nullable=False)
    message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    from_email: Mapped[str] = mapped_column(String(255), nullable=False)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    
    # Relationships
    thread: Mapped["EmailThread"] = relationship("EmailThread", back_populates="messages")
    
    __table_args__ = (
        Index("idx_email_message_thread", "thread_id"),
        Index("idx_email_message_received", "received_at", postgresql_ops={"received_at": "DESC"}),
    )
    
    def __repr__(self) -> str:
        return f"<EmailMessage(id={self.id}, subject='{self.subject}', from='{self.from_email}')>"
