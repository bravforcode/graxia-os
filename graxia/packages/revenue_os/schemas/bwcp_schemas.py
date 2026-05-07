"""
BWCP Message Pydantic Schemas
"""
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..enums import AgentType, BWCPMessageType


class BWCPMessageBase(BaseModel):
    """Base BWCP message schema."""
    conversation_id: str
    sender_agent: AgentType
    recipient_agent: AgentType
    message_type: BWCPMessageType
    belief: Optional[str] = None
    will: Optional[str] = None
    can: Optional[Dict[str, Any]] = None
    plan: Optional[Dict[str, Any]] = None


class BWCPMessageCreate(BWCPMessageBase):
    """Schema for creating BWCP message."""
    campaign_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    approval_id: Optional[UUID] = None
    incident_id: Optional[UUID] = None


class BWCPMessageResponse(BWCPMessageBase):
    """Schema for BWCP message response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    campaign_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    approval_id: Optional[UUID] = None
    incident_id: Optional[UUID] = None
    delivered: bool
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    created_at: datetime


class BWCPMessageList(BaseModel):
    """Schema for paginated BWCP message list."""
    items: List[BWCPMessageResponse]
    total: int
    limit: int
    offset: int


class BWCPConversationResponse(BaseModel):
    """Schema for BWCP conversation thread."""
    conversation_id: str
    messages: List[BWCPMessageResponse]
    message_count: int
    participants: List[str]
    started_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None


class BWCPUnreadCount(BaseModel):
    """Schema for unread message count."""
    recipient_agent: str
    total_undelivered: int
    by_type: Dict[str, int]


class BWCPStats(BaseModel):
    """Schema for BWCP statistics."""
    by_sender: Dict[str, int]
    by_recipient: Dict[str, int]
    by_type: Dict[str, int]
    total_undelivered: int
