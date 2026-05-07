from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SubmissionCreate(BaseModel):
    opportunity_id: UUID | None = None
    contact_id: UUID | None = None
    type: str
    title: str | None = None
    content: str | None = None
    subject_line: str | None = None
    proposed_value: Decimal | None = None
    currency: str | None = None
    follow_up_date: date | None = None


class SubmissionOut(SubmissionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str | None = "draft"
    sent_at: datetime | None = None
    created_at: datetime | None = None
