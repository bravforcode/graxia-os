from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from .base import RuntimeBase


class WorkflowRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class WorkflowRunRef(RuntimeBase):
    workflow_run_id: str = Field(alias="workflowRunId")
    workflow_name: str = Field(alias="workflowName")
    status: WorkflowRunStatus
    started_at: datetime | None = Field(default=None, alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    business_event_id: str | None = Field(default=None, alias="businessEventId")
    context_packet_id: str | None = Field(default=None, alias="contextPacketId")

