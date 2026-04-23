from datetime import date, datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ContactCreate(BaseModel):
    name: str
    role: Optional[str] = None
    company: Optional[str] = None
    contact_type: Optional[str] = None
    email: Optional[str] = None
    telegram_handle: Optional[str] = None
    linkedin_url: Optional[str] = None
    notes: Optional[str] = None
    value_score: Optional[int] = Field(default=None, ge=1, le=10)
    next_followup_date: Optional[date] = None
    followup_reason: Optional[str] = None


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    company: Optional[str] = None
    contact_type: Optional[str] = None
    email: Optional[str] = None
    telegram_handle: Optional[str] = None
    linkedin_url: Optional[str] = None
    notes: Optional[str] = None
    relationship_strength: Optional[int] = Field(default=None, ge=1, le=5)
    last_contacted_at: Optional[date] = None
    value_score: Optional[int] = Field(default=None, ge=1, le=10)
    next_followup_date: Optional[date] = None
    followup_reason: Optional[str] = None


class ContactOut(ContactCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    relationship_strength: Optional[int] = 1
    last_contacted_at: Optional[date] = None
    updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
