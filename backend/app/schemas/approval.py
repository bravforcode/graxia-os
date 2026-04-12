from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ApprovalRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    action_type: str
    subject_type: str | None = None
    subject_id: UUID | None = None
    status: str
    policy_class: str
    requested_by: str | None = None
    batch_key: str | None = None
    details: dict[str, Any] | None = None
    preview: dict[str, Any] | None = None
    expires_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None
    created_at: datetime | None = None


class ApprovalList(BaseModel):
    total: int
    items: list[ApprovalRequestOut]


class ApprovalDecisionResponse(BaseModel):
    id: UUID
    status: str
    batch_key: str | None = None


class ApprovalBatchResponse(BaseModel):
    status: str
    batch_key: str
    count: int
