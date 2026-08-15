"""
Outbox Event Pydantic Schemas
"""
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OutboxEventBase(BaseModel):
    """Base outbox event schema."""
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: Dict[str, Any]
    headers: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None


class OutboxEventCreate(OutboxEventBase):
    """Schema for creating outbox event."""
    pass


class OutboxEventResponse(OutboxEventBase):
    """Schema for outbox event response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    processed: bool
    processed_at: Optional[datetime] = None
    retry_count: int
    last_error: Optional[str] = None
    created_at: datetime


class OutboxEventList(BaseModel):
    """Schema for paginated outbox event list."""
    items: List[OutboxEventResponse]
    total: int
    limit: int
    offset: int


class OutboxStats(BaseModel):
    """Schema for outbox statistics."""
    total: int
    processed: int
    unprocessed: int
    failed: int
    by_aggregate_type: Dict[str, int]
    by_event_type: Dict[str, int]
    avg_processing_seconds: Optional[float] = None


class OutboxRetryRequest(BaseModel):
    """Schema for retry request."""
    reset_retry_count: bool = True
    reason: Optional[str] = None


class OutboxCleanupResponse(BaseModel):
    """Schema for cleanup response."""
    deleted_count: int
    retention_days: int
    cutoff_date: str
