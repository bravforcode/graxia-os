from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AutomationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    task_type: str
    trigger_source: str
    status: str
    idempotency_key: str | None = None
    context: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None


class AutomationRunList(BaseModel):
    total: int
    items: list[AutomationRunOut]
