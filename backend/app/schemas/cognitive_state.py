from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CognitiveStateCreate(BaseModel):
    energy: int = 7
    stress: int = 3
    available_hours_this_week: int = 20
    exam_pressure: int = 0
    mood_note: str | None = None


class CognitiveStateOut(CognitiveStateCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    date: date
    created_at: datetime | None = None
