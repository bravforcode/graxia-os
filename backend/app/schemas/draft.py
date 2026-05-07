from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: UUID
    type: str | None = None
    title: str | None = None
    content: str
    status: str | None = "pending"
    context_notes: str | None = None
    opportunity_id: UUID | None = None
    contact_id: UUID | None = None
    model_used: str | None = None
    was_fallback_draft: bool | None = False
    created_at: datetime | None = None

class DraftList(BaseModel):
    total: int
    items: list[DraftOut]
