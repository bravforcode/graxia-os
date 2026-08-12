from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContactCreate(BaseModel):
    name: str
    role: str | None = None
    company: str | None = None
    contact_type: str | None = None
    status: str | None = "New"
    email: str | None = None
    telegram_handle: str | None = None
    linkedin_url: str | None = None
    notes: str | None = None
    value_score: int | None = Field(default=None, ge=1, le=10)
    next_followup_date: date | None = None
    followup_reason: str | None = None


class ContactUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    company: str | None = None
    contact_type: str | None = None
    status: str | None = None
    email: str | None = None
    telegram_handle: str | None = None
    linkedin_url: str | None = None
    notes: str | None = None
    relationship_strength: int | None = Field(default=None, ge=1, le=5)
    last_contacted_at: date | None = None
    value_score: int | None = Field(default=None, ge=1, le=10)
    next_followup_date: date | None = None
    followup_reason: str | None = None


class ContactOut(ContactCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    relationship_strength: int | None = 1
    last_contacted_at: date | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None
