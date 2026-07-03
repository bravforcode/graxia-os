from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.runtime.contracts import AuditEvent, RiskLevel, TaskEnvelope, TaskStatus, TaskTarget


def utcnow() -> datetime:
    return datetime.now(UTC)


class GatewayIntakeRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    intake_id: UUID = Field(default_factory=uuid4, alias="intakeId")
    task_id: UUID = Field(alias="taskId")
    correlation_id: str = Field(alias="correlationId")
    status: TaskStatus
    risk_level: RiskLevel = Field(alias="riskLevel")
    approval_required: bool = Field(alias="approvalRequired")
    reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow, alias="createdAt")


class GatewayDispatchRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    dispatch_id: UUID = Field(default_factory=uuid4, alias="dispatchId")
    task_id: UUID = Field(alias="taskId")
    correlation_id: str = Field(alias="correlationId")
    target: TaskTarget
    status: TaskStatus
    risk_level: RiskLevel = Field(alias="riskLevel")
    summary: str
    error_message: str | None = Field(default=None, alias="errorMessage")
    approval_request_id: UUID | None = Field(default=None, alias="approvalRequestId")
    run_id: UUID | None = Field(default=None, alias="runId")
    dead_lettered: bool = Field(default=False, alias="deadLettered")
    replay_of_task_id: UUID | None = Field(default=None, alias="replayOfTaskId")
    created_at: datetime = Field(default_factory=utcnow, alias="createdAt")


class GatewayTaskStatusRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    task_id: UUID = Field(alias="taskId")
    correlation_id: str = Field(alias="correlationId")
    target: TaskTarget
    status: TaskStatus
    risk_level: RiskLevel = Field(alias="riskLevel")
    approval_request_id: UUID | None = Field(default=None, alias="approvalRequestId")
    run_id: UUID | None = Field(default=None, alias="runId")
    dead_lettered: bool = Field(default=False, alias="deadLettered")
    updated_at: datetime = Field(default_factory=utcnow, alias="updatedAt")


class GatewayDeadLetterRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    dead_letter_id: UUID = Field(default_factory=uuid4, alias="deadLetterId")
    task_id: UUID = Field(alias="taskId")
    correlation_id: str = Field(alias="correlationId")
    target: TaskTarget
    risk_level: RiskLevel = Field(alias="riskLevel")
    reason: str
    error_message: str = Field(alias="errorMessage")
    replay_count: int = Field(default=0, alias="replayCount")
    task_payload: dict[str, Any] = Field(default_factory=dict, alias="taskPayload")
    created_at: datetime = Field(default_factory=utcnow, alias="createdAt")


class InMemoryGatewayRepository:
    def __init__(self) -> None:
        self._intake_records: dict[UUID, GatewayIntakeRecord] = {}
        self._dispatch_records: dict[UUID, GatewayDispatchRecord] = {}
        self._status_records: dict[UUID, GatewayTaskStatusRecord] = {}
        self._dead_letters: dict[UUID, GatewayDeadLetterRecord] = {}
        self._dead_letters_by_task: dict[UUID, UUID] = {}
        self._audit_events: list[AuditEvent] = []
        self._tasks: dict[UUID, TaskEnvelope] = {}
        self._idempotency_index: dict[str, UUID] = {}

    def remember_task(self, task: TaskEnvelope) -> None:
        self._tasks[task.task_id] = task

    def get_task(self, task_id: UUID) -> TaskEnvelope | None:
        return self._tasks.get(task_id)

    def get_dispatch_by_idempotency(self, key: str) -> GatewayDispatchRecord | None:
        task_id = self._idempotency_index.get(key)
        if task_id is None:
            return None
        return self._dispatch_records.get(task_id)

    def save_intake(self, record: GatewayIntakeRecord) -> GatewayIntakeRecord:
        self._intake_records[record.task_id] = record
        return record

    def save_dispatch(
        self,
        record: GatewayDispatchRecord,
        *,
        idempotency_key: str | None = None,
    ) -> GatewayDispatchRecord:
        self._dispatch_records[record.task_id] = record
        self._status_records[record.task_id] = GatewayTaskStatusRecord(
            taskId=record.task_id,
            correlationId=record.correlation_id,
            target=record.target,
            status=record.status,
            riskLevel=record.risk_level,
            approvalRequestId=record.approval_request_id,
            runId=record.run_id,
            deadLettered=record.dead_lettered,
        )
        if idempotency_key:
            self._idempotency_index[idempotency_key] = record.task_id
        return record

    def get_dispatch(self, task_id: UUID) -> GatewayDispatchRecord | None:
        return self._dispatch_records.get(task_id)

    def get_status(self, task_id: UUID) -> GatewayTaskStatusRecord | None:
        return self._status_records.get(task_id)

    def list_statuses(self, limit: int = 20) -> list[GatewayTaskStatusRecord]:
        return sorted(
            self._status_records.values(),
            key=lambda item: item.updated_at,
            reverse=True,
        )[:limit]

    def add_dead_letter(self, record: GatewayDeadLetterRecord) -> GatewayDeadLetterRecord:
        self._dead_letters[record.dead_letter_id] = record
        self._dead_letters_by_task[record.task_id] = record.dead_letter_id
        return record

    def get_dead_letter(self, dead_letter_id: UUID) -> GatewayDeadLetterRecord | None:
        return self._dead_letters.get(dead_letter_id)

    def get_dead_letter_for_task(self, task_id: UUID) -> GatewayDeadLetterRecord | None:
        dead_letter_id = self._dead_letters_by_task.get(task_id)
        if dead_letter_id is None:
            return None
        return self._dead_letters.get(dead_letter_id)

    def clear_dead_letter(self, dead_letter_id: UUID) -> None:
        record = self._dead_letters.pop(dead_letter_id, None)
        if record is not None:
            self._dead_letters_by_task.pop(record.task_id, None)

    def list_dead_letters(self, limit: int = 20) -> list[GatewayDeadLetterRecord]:
        return sorted(
            self._dead_letters.values(),
            key=lambda item: item.created_at,
            reverse=True,
        )[:limit]

    def add_audit_event(self, event: AuditEvent) -> AuditEvent:
        self._audit_events.append(event)
        return event

    def list_audit_events(self, limit: int = 20) -> list[AuditEvent]:
        return self._audit_events[-limit:][::-1]
