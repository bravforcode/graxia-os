from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class DraftOut(BaseModel):
    id: UUID
    type: Optional[str] = None
    title: Optional[str] = None
    content: str
    status: Optional[str] = "pending"
    context_notes: Optional[str] = None
    opportunity_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    model_used: Optional[str] = None
    was_fallback_draft: Optional[bool] = False
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DraftList(BaseModel):
    total: int
    items: list[DraftOut]
