from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.runtime.contracts import WorkflowRunRef


def utcnow() -> datetime:
    return datetime.now(UTC)


class WorkflowTraceRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    workflow: WorkflowRunRef
    correlation_id: str = Field(alias="correlationId")
    organization_id: str = Field(alias="organizationId")
    workflow_name: str = Field(alias="workflowName")
    execution_mode: str = Field(alias="executionMode")
    business_event_id: str | None = Field(default=None, alias="businessEventId")
    context_packet_id: str | None = Field(default=None, alias="contextPacketId")
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow, alias="createdAt")


class WorkflowTraceStore:
    def __init__(self) -> None:
        self._records: list[WorkflowTraceRecord] = []

    def save(self, record: WorkflowTraceRecord) -> WorkflowTraceRecord:
        self._records.append(record)
        return record

    def list(
        self,
        *,
        organization_id: str | None = None,
        correlation_id: str | None = None,
        workflow_name: str | None = None,
        limit: int = 20,
    ) -> list[WorkflowTraceRecord]:
        records = self._records
        if organization_id:
            records = [item for item in records if item.organization_id == organization_id]
        if correlation_id:
            records = [item for item in records if item.correlation_id == correlation_id]
        if workflow_name:
            records = [item for item in records if item.workflow_name == workflow_name]
        return records[-limit:][::-1]

    def clear(self) -> None:
        self._records.clear()


workflow_trace_store = WorkflowTraceStore()
