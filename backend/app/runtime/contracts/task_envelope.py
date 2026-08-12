from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field

from .base import RuntimeBase


class TaskTarget(StrEnum):
    GATEWAY = "gateway"
    WORKER = "worker"
    WORKFLOW = "workflow"
    MCP = "mcp"
    GRAXIA = "graxia"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskEnvelope(RuntimeBase):
    task_id: UUID = Field(default_factory=uuid4, alias="taskId")
    target: TaskTarget
    task_type: str = Field(alias="taskType")
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    business_event_id: UUID | None = Field(default=None, alias="businessEventId")
    context_packet_id: UUID | None = Field(default=None, alias="contextPacketId")
    approval_request_id: UUID | None = Field(default=None, alias="approvalRequestId")
    payload: dict[str, Any] = Field(default_factory=dict)

