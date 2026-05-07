"""Assistant task model for task management."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class AssistantTask(Base, TenantMixin):
    """
    Assistant task model for managing tasks and reminders.
    
    Attributes:
        id: Unique identifier
        title: Task title
        description: Task description
        task_type: Type of task (email, application, follow_up, meeting)
        priority: Priority level (1-10)
        status: Task status (pending, in_progress, completed, cancelled)
        due_date: When task is due
        related_entity_type: Type of related entity (job_posting, contact, email_thread)
        related_entity_id: ID of related entity
        assigned_to: Who task is assigned to (user, agent_name)
        completed_at: When task was completed
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    
    __tablename__ = "assistant_tasks"
    
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    task_type: Mapped[str | None] = mapped_column(String(50))
    priority: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    status: Mapped[str] = mapped_column(String(50), default="pending", server_default="pending", index=True)
    due_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), index=True)
    related_entity_type: Mapped[str | None] = mapped_column(String(50))
    related_entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    assigned_to: Mapped[str] = mapped_column(String(100), default="user", server_default="user")
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), 
        default=lambda: datetime.now(UTC), 
        onupdate=lambda: datetime.now(UTC)
    )
    
    __table_args__ = (
        Index("idx_task_priority", "priority", postgresql_ops={"priority": "DESC"}),
        Index("idx_task_related", "related_entity_type", "related_entity_id"),
        Index("idx_task_status_priority", "status", "priority", postgresql_ops={"priority": "DESC"}),
    )
    
    def __repr__(self) -> str:
        return f"<AssistantTask(id={self.id}, title='{self.title}', status='{self.status}')>"
    
    @property
    def is_pending(self) -> bool:
        """Check if task is pending."""
        return self.status == "pending"
    
    @property
    def is_completed(self) -> bool:
        """Check if task is completed."""
        return self.status == "completed"
    
    @property
    def is_overdue(self) -> bool:
        """Check if task is overdue."""
        if not self.due_date or self.is_completed:
            return False
        return datetime.now(UTC) > self.due_date
    
    @property
    def is_urgent(self) -> bool:
        """Check if task is urgent (priority >= 9 or due within 24 hours)."""
        if self.priority >= 9:
            return True
        if self.due_date:
            hours_until_due = (
                self.due_date - datetime.now(UTC)
            ).total_seconds() / 3600
            return hours_until_due <= 24
        return False
    
    @property
    def days_until_due(self) -> int | None:
        """Get number of days until task is due."""
        if not self.due_date:
            return None
        delta = self.due_date - datetime.now(UTC)
        return delta.days
    
    def mark_in_progress(self) -> None:
        """Mark task as in progress."""
        self.status = "in_progress"
    
    def mark_completed(self) -> None:
        """Mark task as completed."""
        self.status = "completed"
        self.completed_at = datetime.now(UTC)
    
    def mark_cancelled(self) -> None:
        """Mark task as cancelled."""
        self.status = "cancelled"
    
    def set_priority(self, priority: int) -> None:
        """Set task priority (1-10)."""
        if not 1 <= priority <= 10:
            raise ValueError("Priority must be between 1 and 10")
        self.priority = priority
