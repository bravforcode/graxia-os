from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from app.core.event_bus import event_bus
from app.core.policy import build_batch_key, get_action_policy
from app.database import AsyncSessionLocal
from app.models.approval_request import ApprovalRequest
from app.models.automation_run import AutomationRun
from app.models.content_draft import ContentDraft
from app.telegram_bot.bot import send_message
from app.telegram_bot.keyboards import approval_keyboard


class ApprovalAlreadyProcessedError(RuntimeError):
    def __init__(self, status: str):
        super().__init__("Approval already processed")
        self.status = status


def _approval_event_payload(approval: ApprovalRequest) -> dict[str, Any]:
    return {
        "approval_id": str(approval.id),
        "title": approval.title,
        "action_type": approval.action_type,
        "status": approval.status,
        "policy_class": approval.policy_class,
        "requested_by": approval.requested_by,
        "batch_key": approval.batch_key,
        "subject_type": approval.subject_type,
        "subject_id": str(approval.subject_id) if approval.subject_id else None,
        "details": approval.details or {},
        "preview": approval.preview or {},
        "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
        "resolved_at": approval.resolved_at.isoformat() if approval.resolved_at else None,
        "resolution_note": approval.resolution_note,
    }


async def create_run(
    name: str,
    task_type: str,
    trigger_source: str,
    context: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> AutomationRun:
    async with AsyncSessionLocal() as db:
        run = AutomationRun(
            name=name,
            task_type=task_type,
            trigger_source=trigger_source,
            context=context or {},
            idempotency_key=idempotency_key,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run


async def mark_run_started(run_id: UUID) -> None:
    async with AsyncSessionLocal() as db:
        run = await db.get(AutomationRun, run_id)
        if not run:
            return
        run.status = "running"
        run.started_at = datetime.now(UTC)
        await db.commit()


async def mark_run_completed(run_id: UUID, result: dict[str, Any] | None = None) -> None:
    async with AsyncSessionLocal() as db:
        run = await db.get(AutomationRun, run_id)
        if not run:
            return
        run.status = "completed"
        run.result = result or {}
        run.completed_at = datetime.now(UTC)
        await db.commit()


async def mark_run_failed(run_id: UUID, error_message: str) -> None:
    async with AsyncSessionLocal() as db:
        run = await db.get(AutomationRun, run_id)
        if not run:
            return
        run.status = "failed"
        run.error_message = error_message
        run.completed_at = datetime.now(UTC)
        await db.commit()


async def queue_approval_request(
    title: str,
    action_type: str,
    subject_type: str | None = None,
    subject_id: UUID | None = None,
    details: dict[str, Any] | None = None,
    preview: dict[str, Any] | None = None,
    requested_by: str | None = None,
    batch_group: str | None = None,
) -> ApprovalRequest:
    policy = get_action_policy(action_type)
    expires_at = None
    if policy.default_ttl_hours > 0:
        expires_at = datetime.now(UTC) + timedelta(hours=policy.default_ttl_hours)

    approval = ApprovalRequest(
        title=title,
        action_type=action_type,
        subject_type=subject_type,
        subject_id=subject_id,
        policy_class=policy.policy_class,
        requested_by=requested_by,
        details=details or {},
        preview=preview or {},
        batch_key=build_batch_key(action_type, subject_type, batch_group)
        if policy.batchable
        else None,
        expires_at=expires_at,
    )

    async with AsyncSessionLocal() as db:
        db.add(approval)
        await db.commit()
        await db.refresh(approval)

    await _notify_approval_request(approval)
    await event_bus.emit("approval.requested", _approval_event_payload(approval))
    return approval


async def create_draft_review_request(
    draft_id: UUID,
    draft_type: str | None,
    draft_title: str | None,
    preview_text: str,
    requested_by: str,
) -> ApprovalRequest:
    return await queue_approval_request(
        title=draft_title or "Draft review",
        action_type="draft_review",
        subject_type="content_draft",
        subject_id=draft_id,
        details={"draft_type": draft_type or "other"},
        preview={"content_preview": preview_text[:280]},
        requested_by=requested_by,
        batch_group=draft_type or "draft",
    )


async def resolve_approval_request(
    approval_id: UUID,
    decision: str,
    note: str | None = None,
) -> ApprovalRequest | None:
    async with AsyncSessionLocal() as db:
        approval = await db.get(ApprovalRequest, approval_id)
        if approval is None:
            return None
        if approval.status != "pending":
            raise ApprovalAlreadyProcessedError(approval.status)

        resolved_at = datetime.now(UTC)
        approval.status = "approved" if decision == "approved" else "rejected"
        approval.resolved_at = resolved_at
        approval.resolution_note = note

        if approval.subject_type == "content_draft" and approval.subject_id:
            draft = await db.get(ContentDraft, approval.subject_id)
            if draft:
                if decision == "approved":
                    draft.status = "approved"
                    draft.approved_at = resolved_at
                else:
                    draft.status = "rejected"
                    draft.rejection_reason = note or "Rejected from approval queue"

        await db.commit()
        await db.refresh(approval)

    await event_bus.emit("approval.resolved", _approval_event_payload(approval))
    if decision == "approved" and approval.subject_type == "content_draft" and approval.subject_id:
        await event_bus.emit(
            "draft.approved",
            {"draft_id": str(approval.subject_id), "draft_type": approval.details.get("draft_type")},
        )
    return approval


async def resolve_approval_batch(
    batch_key: str,
    decision: str,
    note: str | None = None,
) -> int:
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(ApprovalRequest).where(
                        ApprovalRequest.batch_key == batch_key,
                        ApprovalRequest.status == "pending",
                    )
                )
            ).scalars()
        )
        approval_ids = [row.id for row in rows]

    count = 0
    for approval_id in approval_ids:
        approval = await resolve_approval_request(approval_id, decision, note=note)
        if approval is not None:
            count += 1
    return count


async def mark_subject_approvals_resolved(
    subject_type: str,
    subject_id: UUID,
    decision: str,
    note: str | None = None,
) -> int:
    async with AsyncSessionLocal() as db:
        resolved_at = datetime.now(UTC)
        rows = list(
            (
                await db.execute(
                    select(ApprovalRequest).where(
                        ApprovalRequest.subject_type == subject_type,
                        ApprovalRequest.subject_id == subject_id,
                        ApprovalRequest.status == "pending",
                    )
                )
            ).scalars()
        )

        payloads: list[dict[str, Any]] = []
        for approval in rows:
            approval.status = "approved" if decision == "approved" else "rejected"
            approval.resolved_at = resolved_at
            approval.resolution_note = note
            payloads.append(_approval_event_payload(approval))
        await db.commit()

    for payload in payloads:
        await event_bus.emit("approval.resolved", payload)
    return len(rows)


async def count_pending_approvals() -> int:
    async with AsyncSessionLocal() as db:
        total = await db.scalar(
            select(func.count()).select_from(
                select(ApprovalRequest)
                .where(ApprovalRequest.status == "pending")
                .subquery()
            )
        )
    return int(total or 0)


async def _notify_approval_request(approval: ApprovalRequest) -> None:
    expires_at = approval.expires_at.isoformat() if approval.expires_at else "no expiry"
    await send_message(
        (
            "🛂 *Approval Required*\n\n"
            f"*{approval.title}*\n"
            f"Action: `{approval.action_type}`\n"
            f"Requested by: `{approval.requested_by or 'system'}`\n"
            f"Expires: `{expires_at}`"
        ),
        reply_markup=approval_keyboard(str(approval.id), approval.batch_key),
    )
