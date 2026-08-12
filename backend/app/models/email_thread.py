"""Email thread model for managing email conversations."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, Boolean, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TenantMixin


class EmailThread(Base, TenantMixin):
    """
    Email thread model for grouping related emails.
    
    Attributes:
        id: Unique identifier
        thread_id: Gmail thread ID (unique)
        subject: Email subject line
        participants: List of participants with email and name
        category: Email category (urgent, important, normal, spam, newsletter)
        priority: Priority level (1-10)
        last_message_at: Timestamp of last message in thread
        unread_count: Number of unread messages
        has_attachments: Whether thread has attachments
        action_items: Extracted action items from emails
        status: Thread status (unread, read, replied, archived)
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    
    __tablename__ = "email_threads"
    
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    thread_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    subject: Mapped[str | None] = mapped_column(String(500))
    participants: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    category: Mapped[str | None] = mapped_column(String(50), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    last_message_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    unread_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    action_items: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    status: Mapped[str] = mapped_column(String(50), default="unread", server_default="unread")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    
    # Relationships
    messages: Mapped[list["EmailMessage"]] = relationship(
        "EmailMessage",
        back_populates="thread",
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index("idx_email_priority", "priority", postgresql_ops={"priority": "DESC"}),
        Index("idx_email_last_message", "last_message_at", postgresql_ops={"last_message_at": "DESC"}),
    )
    
    def __repr__(self) -> str:
        return f"<EmailThread(id={self.id}, subject='{self.subject}', status='{self.status}')>"
    
    @property
    def is_urgent(self) -> bool:
        """Check if thread is urgent (priority >= 9)."""
        return self.priority >= 9
    
    @property
    def is_unread(self) -> bool:
        """Check if thread has unread messages."""
        return self.unread_count > 0
    
    def add_action_item(self, task: str, due_date: datetime | None = None, priority: int = 5) -> None:
        """Add an action item to the thread."""
        if not self.action_items:
            self.action_items = []
        
        action_item = {
            "task": task,
            "due_date": due_date.isoformat() if due_date else None,
            "priority": priority,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.action_items.append(action_item)
    
    def mark_as_read(self) -> None:
        """Mark thread as read."""
        self.status = "read"
        self.unread_count = 0
    
    def mark_as_replied(self) -> None:
        """Mark thread as replied."""
        self.status = "replied"
        self.unread_count = 0
