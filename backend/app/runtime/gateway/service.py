from __future__ import annotations

from typing import Any, Awaitable, Callable
from uuid import UUID

from app.core.control_plane import (
    create_run as default_create_run,
    mark_run_completed as default_mark_run_completed,
    mark_run_failed as default_mark_run_failed,
    mark_run_started as default_mark_run_started,
    queue_approval_request as default_queue_approval_request,
)
from app.runtime.contracts import ActorType, AuditEvent, RiskLevel, TaskEnvelope, TaskStatus
from app.runtime.gateway.dispatcher import DispatchResult, GatewayDispatcher
from app.runtime.gateway.errors import ApprovalRequiredError, DangerousTaskBlockedError
from app.runtime.gateway.policy import GatewayPolicyDecision, evaluate_task_policy
from app.runtime.gateway.repository import (
    GatewayDeadLetterRecord,
    GatewayDispatchRecord,
    GatewayIntakeRecord,
    GatewayTaskStatusRecord,
    InMemoryGatewayRepository,
)

ApprovalRequester = Callable[..., Awaitable[Any]]
RunCreator = Callable[..., Awaitable[Any]]
RunMarker = Callable[..., Awaitable[None]]

_SECRET_MARKERS = ("token", "secret", "password", "cookie")


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if any(marker in lowered for marker in _SECRET_MARKERS):
                continue
            sanitized[key] = _sanitize_payload(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    return value


def _coerce_uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _extract_idempotency_key(task: TaskEnvelope) -> str | None:
    payload = task.payload or {}
    raw = payload.get("idempotency_key") or payload.get("idempotencyKey")
    return str(raw) if raw else None


def _build_audit_event(
    *,
    task: TaskEnvelope,
    decision: GatewayPolicyDecision,
    event_type: str,
    subject_id: str,
    payload: dict[str, Any],
) -> AuditEvent:
    return AuditEvent(
        organizationId=task.organization_id,
        correlationId=task.correlation_id,
        source="runtime_gateway",
        eventType=event_type,
        actorType=ActorType.SYSTEM,
        actorId="runtime_gateway",
        subjectType="task",
        subjectId=subject_id,
        riskLevel=decision.risk_level,
        redactedPayload=_sanitize_payload(payload),
    )


class GatewayService:
    def __init__(
        self,
        *,
        repository: InMemoryGatewayRepository | None = None,
        dispatcher: GatewayDispatcher | None = None,
        approval_requester: ApprovalRequester | None = default_queue_approval_request,
        run_creator: RunCreator | None = default_create_run,
        run_started: RunMarker | None = default_mark_run_started,
        run_completed: RunMarker | None = default_mark_run_completed,
        run_failed: RunMarker | None = default_mark_run_failed,
    ) -> None:
        self.repository = repository or InMemoryGatewayRepository()
        self.dispatcher = dispatcher or GatewayDispatcher()
        self.approval_requester = approval_requester
        self.run_creator = run_creator
        self.run_started = run_started
        self.run_completed = run_completed
        self.run_failed = run_failed

    def _parse_task(self, input_value: Any) -> TaskEnvelope:
        if isinstance(input_value, TaskEnvelope):
            return input_value
        return TaskEnvelope.model_validate(input_value)

    async def intake(self, input_value: Any) -> GatewayIntakeRecord:
        task = self._parse_task(input_value)
        decision = evaluate_task_policy(task)
        record = GatewayIntakeRecord(
            taskId=task.task_id,
            correlationId=task.correlation_id,
            status=TaskStatus.PENDING,
            riskLevel=decision.risk_level,
            approvalRequired=decision.approval_required,
            reasons=decision.reasons,
        )
        self.repository.remember_task(task)
        self.repository.save_intake(record)
        self.repository.add_audit_event(
            _build_audit_event(
                task=task,
                decision=decision,
                event_type="runtime.gateway.intake",
                subject_id=str(task.task_id),
                payload={
                    "taskType": task.task_type,
                    "target": task.target,
                    "approvalRequired": decision.approval_required,
                    "reasons": decision.reasons,
                },
            )
        )
        return record

    async def dispatch_task(self, input_value: Any) -> GatewayDispatchRecord:
        task = self._parse_task(input_value)
        idempotency_key = _extract_idempotency_key(task)
        if idempotency_key:
            existing = self.repository.get_dispatch_by_idempotency(idempotency_key)
            if existing is not None:
                return existing

        await self.intake(task)
        decision = evaluate_task_policy(task)

        if decision.dangerous_blocked:
            return self._store_blocked_dispatch(task, decision, DangerousTaskBlockedError(decision.reasons[0]), idempotency_key)

        if decision.approval_required:
            approval_request_id = await self._queue_approval(task, decision)
            record = GatewayDispatchRecord(
                taskId=task.task_id,
                correlationId=task.correlation_id,
                target=task.target,
                status=TaskStatus.BLOCKED,
                riskLevel=decision.risk_level,
                summary="Dispatch blocked pending approval",
                approvalRequestId=approval_request_id,
            )
            self.repository.save_dispatch(record, idempotency_key=idempotency_key)
            self.repository.add_audit_event(
                _build_audit_event(
                    task=task,
                    decision=decision,
                    event_type="runtime.gateway.approval_blocked",
                    subject_id=str(task.task_id),
                    payload={
                        "approvalRequestId": str(approval_request_id),
                        "taskType": task.task_type,
                    },
                )
            )
            return record

        run_id = await self._create_run(task)
        try:
            result = await self.dispatcher.dispatch(task)
        except Exception as exc:
            if run_id and self.run_failed:
                await self.run_failed(run_id, str(exc))
            dead_letter = self.repository.add_dead_letter(
                GatewayDeadLetterRecord(
                    taskId=task.task_id,
                    correlationId=task.correlation_id,
                    target=task.target,
                    riskLevel=decision.risk_level,
                    reason="dispatch_failed",
                    errorMessage=str(exc),
                    taskPayload=_sanitize_payload(task.model_dump(by_alias=True)),
                )
            )
            record = GatewayDispatchRecord(
                taskId=task.task_id,
                correlationId=task.correlation_id,
                target=task.target,
                status=TaskStatus.FAILED,
                riskLevel=decision.risk_level,
                summary="Dispatch failed and moved to dead letter",
                errorMessage=str(exc),
                runId=run_id,
                deadLettered=True,
            )
            self.repository.save_dispatch(record, idempotency_key=idempotency_key)
            self.repository.add_audit_event(
                _build_audit_event(
                    task=task,
                    decision=decision,
                    event_type="runtime.gateway.dead_lettered",
                    subject_id=str(dead_letter.dead_letter_id),
                    payload={
                        "taskId": str(task.task_id),
                        "errorMessage": str(exc),
                    },
                )
            )
            return record

        if run_id and self.run_completed:
            await self.run_completed(
                run_id,
                {
                    "summary": result.summary,
                    "target": result.target,
                    "status": result.status,
                },
            )
        record = GatewayDispatchRecord(
            taskId=task.task_id,
            correlationId=task.correlation_id,
            target=result.target,
            status=result.status,
            riskLevel=decision.risk_level,
            summary=result.summary,
            errorMessage=result.error_message,
            runId=run_id or result.run_id,
        )
        self.repository.save_dispatch(record, idempotency_key=idempotency_key)
        self.repository.add_audit_event(
            _build_audit_event(
                task=task,
                decision=decision,
                event_type="runtime.gateway.dispatched",
                subject_id=str(task.task_id),
                payload={
                    "target": result.target,
                    "status": result.status,
                    "summary": result.summary,
                },
            )
        )
        return record

    async def replay_task(self, input_value: Any) -> GatewayDispatchRecord:
        dead_letter_id = _coerce_uuid(
            input_value.get("deadLetterId") if isinstance(input_value, dict) else input_value
        )
        if dead_letter_id is None:
            raise ValueError("deadLetterId is required")
        dead_letter = self.repository.get_dead_letter(dead_letter_id)
        if dead_letter is None:
            raise KeyError(f"Unknown dead letter: {dead_letter_id}")
        original_task = self.repository.get_task(dead_letter.task_id)
        if original_task is None:
            raise KeyError(f"Unknown task for dead letter: {dead_letter.task_id}")
        replay_task = TaskEnvelope.model_validate(
            {
                **original_task.model_dump(by_alias=True),
                "taskId": str(original_task.task_id),
                "payload": {
                    **original_task.payload,
                    "idempotencyKey": f"replay:{original_task.task_id}:{dead_letter.replay_count + 1}",
                },
            }
        )
        result = await self.dispatch_task(replay_task)
        dead_letter.replay_count += 1
        self.repository.clear_dead_letter(dead_letter_id)
        return GatewayDispatchRecord(
            **{
                **result.model_dump(by_alias=True),
                "replayOfTaskId": original_task.task_id,
            }
        )

    async def requeue_dead_letter(self, input_value: Any) -> GatewayDispatchRecord:
        return await self.replay_task(input_value)

    async def preview_approval(self, input_value: Any) -> dict[str, Any]:
        task = self._parse_task(input_value)
        decision = evaluate_task_policy(task)
        preview: dict[str, Any] | None = None
        if decision.approval_required:
            preview = {
                "title": f"Approve runtime task: {task.task_type}",
                "subject_type": "runtime_task",
                "subject_id": str(task.task_id),
                "requested_by": "runtime_gateway",
            }
        return {
            "task": task,
            "decision": decision,
            "approval": preview,
        }

    async def list_audit_events(self, limit: int = 20) -> list[AuditEvent]:
        return self.repository.list_audit_events(limit)

    async def get_dispatch_record(self, task_id: UUID) -> GatewayDispatchRecord | None:
        return self.repository.get_dispatch(task_id)

    async def get_task_status(self, task_id: UUID) -> GatewayTaskStatusRecord | None:
        return self.repository.get_status(task_id)

    async def list_dead_letters(self, limit: int = 20) -> list[GatewayDeadLetterRecord]:
        return self.repository.list_dead_letters(limit)

    async def _queue_approval(self, task: TaskEnvelope, decision: GatewayPolicyDecision) -> UUID:
        if self.approval_requester is None:
            raise ApprovalRequiredError("approval requester is not configured")
        subject_id = _coerce_uuid(task.payload.get("subject_id") or task.payload.get("subjectId"))
        approval = await self.approval_requester(
            title=f"Approve runtime task: {task.task_type}",
            action_type=task.task_type,
            subject_type="runtime_task",
            subject_id=subject_id,
            details={
                "task_id": str(task.task_id),
                "target": task.target,
                "reasons": decision.reasons,
            },
            preview={
                "taskType": task.task_type,
                "payload": _sanitize_payload(task.payload),
            },
            requested_by="runtime_gateway",
        )
        approval_id = _coerce_uuid(getattr(approval, "id", None) or getattr(approval, "approval_request_id", None))
        return approval_id or UUID(int=0)

    async def _create_run(self, task: TaskEnvelope) -> UUID | None:
        if self.run_creator is None:
            return None
        run = await self.run_creator(
            name=f"runtime:{task.task_type}",
            task_type=task.task_type,
            trigger_source="runtime_gateway",
            context={
                "task_id": str(task.task_id),
                "correlation_id": task.correlation_id,
                "target": task.target,
            },
            idempotency_key=_extract_idempotency_key(task),
        )
        run_id = _coerce_uuid(getattr(run, "id", None))
        if run_id and self.run_started:
            await self.run_started(run_id)
        return run_id

    def _store_blocked_dispatch(
        self,
        task: TaskEnvelope,
        decision: GatewayPolicyDecision,
        error: Exception,
        idempotency_key: str | None,
    ) -> GatewayDispatchRecord:
        record = GatewayDispatchRecord(
            taskId=task.task_id,
            correlationId=task.correlation_id,
            target=task.target,
            status=TaskStatus.BLOCKED,
            riskLevel=decision.risk_level,
            summary="Dispatch blocked by gateway policy",
            errorMessage=str(error),
        )
        self.repository.save_dispatch(record, idempotency_key=idempotency_key)
        self.repository.add_audit_event(
            _build_audit_event(
                task=task,
                decision=decision,
                event_type="runtime.gateway.blocked",
                subject_id=str(task.task_id),
                payload={"errorMessage": str(error), "reasons": decision.reasons},
            )
        )
        return record


gateway_repository = InMemoryGatewayRepository()
gateway_service = GatewayService(repository=gateway_repository)
