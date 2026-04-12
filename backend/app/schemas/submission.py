from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class SubmissionCreate(BaseModel):
    opportunity_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    type: str
    title: Optional[str] = None
    content: Optional[str] = None
    subject_line: Optional[str] = None
    proposed_value: Optional[Decimal] = None
    follow_up_date: Optional[date] = None


class SubmissionOut(SubmissionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: Optional[str] = "draft"
    sent_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
