from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class ContactCreate(BaseModel):
    name: str
    role: Optional[str] = None
    company: Optional[str] = None
    contact_type: Optional[str] = None
    email: Optional[str] = None
    telegram_handle: Optional[str] = None
    linkedin_url: Optional[str] = None
    notes: Optional[str] = None
    value_score: Optional[int] = None
    next_followup_date: Optional[date] = None
    followup_reason: Optional[str] = None


class ContactOut(ContactCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    relationship_strength: Optional[int] = 1
    last_contacted_at: Optional[date] = None
    created_at: Optional[datetime] = None
