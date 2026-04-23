import uuid
from sqlalchemy import (
    UUID, Column, DateTime, String, Text, func, ForeignKey
)
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base

class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    assigned_to = Column(String(50), nullable=False)
    assigned_by = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, default="pending")  # pending, in_progress, completed, failed, waiting
    result = Column(JSONB, nullable=True)
    
    parent_id = Column(UUID(as_uuid=True), ForeignKey("agent_tasks.id"), nullable=True)
    dependencies = Column(JSONB, default=list) # List of UUIDs that must be completed first
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(255), nullable=False, index=True) # E.g., meeting topic hash or task id
    sender = Column(String(50), nullable=False)
    receiver = Column(String(50), nullable=True) # None = broadcast/meeting
    content = Column(Text, nullable=False)
    
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
