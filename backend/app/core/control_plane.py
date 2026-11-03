from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update

from app.config import settings
from app.auth.context import AuthContext

from app.core.event_bus import event_bus
from app.core.policy import build_batch_key, get_action_policy
from app.database import AsyncSessionLocal
from app.models.approval_request import ApprovalRequest
from app.models.automation_run import AutomationRun
from app.models.content_draft import ContentDraft
from app.models.telegram_pairing import TelegramApprovalBinding
from app.services.audit_service import log_audit_event
from app.services.telegram_pairing import resolve_telegram_auth_context
from app.telegram_bot.bot import send_message
from app.telegram_bot.keyboards import (
    approval_batch_callback_ref,
    approval_keyboard,
    is_approval_batch_callback_ref,
)

logger = logging.getLogger(__name__)


class ApprovalAlreadyProcessedError(RuntimeError):
    def __init__(self, status: str):
        super().__init__("Approval already processed")
        self.status = status


@dataclass(frozen=True)
class ApprovalBatchResolution:
    decision_count: int
    expired_count: int


def _trusted_approval_owner(auth: AuthContext | None) -> UUID:
    if not isinstance(auth, AuthContext) or not auth.is_authenticated or (
        auth.is_staging_or_production and auth.is_mock_auth
    ) or not isinstance(auth.organization_id, UUID) or auth.organization_id.int == 0:
        raise ValueError("approval_authenticated_organization_required")
    return auth.organization_id


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
    organization_id: UUID | None = None,
) -> AutomationRun:
    tenant_id = organization_id or getattr(settings, "LEGACY_ORGANIZATION_ID", UUID("00000000-0000-0000-0000-000000000001"))
    async with AsyncSessionLocal() as db:
        run = AutomationRun(
            organization_id=tenant_id,
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
    *,
    auth: AuthContext | None = None,
) -> ApprovalRequest:
    organization_id = _trusted_approval_owner(auth)
    policy = get_action_policy(action_type)
    expires_at = None
    if policy.default_ttl_hours > 0:
        expires_at = datetime.now(UTC) + timedelta(hours=policy.default_ttl_hours)

    approval = ApprovalRequest(
        organization_id=organization_id,
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
    *,
    auth: AuthContext | None = None,
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
        auth=auth,
    )


async def resolve_approval_request(
    approval_id: UUID,
    decision: str,
    note: str | None = None,
    *,
    organization_id: UUID | None = None,
    audit_actor_id: str | UUID | None = None,
    audit_source: str = "telegram",
    emit_events: bool = True,
    update_related_subject: bool = True,
) -> ApprovalRequest | None:
    if not isinstance(organization_id, UUID) or organization_id.int == 0:
        raise ValueError("approval_organization_required")
    if decision not in {"approved", "rejected"}:
        raise ValueError("approval_decision_invalid")
    async with AsyncSessionLocal() as db:
        approval = await db.get(ApprovalRequest, approval_id)
        if approval is None or approval.organization_id != organization_id:
            return None
        if approval.status != "pending":
            raise ApprovalAlreadyProcessedError(approval.status)

        resolved_at = datetime.now(UTC)
        expires_at = approval.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        expired = expires_at is not None and expires_at <= resolved_at
        outcome = "expired" if expired else decision
        claimed = await db.execute(update(ApprovalRequest).where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.organization_id == organization_id,
            ApprovalRequest.status == "pending",
        ).values(status=outcome, resolved_at=resolved_at, resolution_note=note)
          .returning(ApprovalRequest.id).execution_options(synchronize_session=False))
        if claimed.scalar_one_or_none() is None:
            await db.rollback()
            raise ApprovalAlreadyProcessedError("already_consumed")

        # The conditional update intentionally bypasses ORM synchronization so
        # the database remains authoritative for the one-time claim. Mirror the
        # winning update into the loaded object before audit flush/readback.
        approval.status = outcome
        approval.resolved_at = resolved_at
        approval.resolution_note = note

        if (
            update_related_subject
            and not expired
            and approval.subject_type == "content_draft"
            and approval.subject_id
        ):
            draft = await db.get(ContentDraft, approval.subject_id)
            if draft and draft.organization_id == organization_id:
                if decision == "approved":
                    draft.status = "approved"
                    draft.approved_at = resolved_at
                else:
                    draft.status = "rejected"
                    draft.rejection_reason = note or "Rejected from approval queue"

        if audit_actor_id is not None:
            actor_id = str(audit_actor_id)
            await log_audit_event(
                db=db,
                action=f"approval.{outcome}",
                event_type="approval.resolved",
                event_category="approval",
                outcome="success",
                metadata={
                    "actor_id": actor_id,
                    "channel": audit_source,
                    "decision": decision,
                    "organization_id": str(organization_id),
                    "status": outcome,
                },
                details={
                    "approval_id": str(approval.id),
                    "actor_id": actor_id,
                    "decision": decision,
                    "organization_id": str(organization_id),
                    "status": outcome,
                },
                triggered_by=audit_source,
                user_id=actor_id,
                entity_type="approval_request",
                entity_id=str(approval.id),
            )

        await db.commit()
        await db.refresh(approval)

    if emit_events:
        await event_bus.emit("approval.resolved", _approval_event_payload(approval))
    if (
        emit_events
        and update_related_subject
        and not expired
        and decision == "approved"
        and approval.subject_type == "content_draft"
        and approval.subject_id
    ):
        await event_bus.emit(
            "draft.approved",
            {"draft_id": str(approval.subject_id), "draft_type": approval.details.get("draft_type")},
        )
    return approval


async def resolve_approval_batch(
    batch_key: str,
    decision: str,
    note: str | None = None,
    organization_id: UUID | None = None,
    *,
    audit_actor_id: str | UUID | None = None,
    audit_source: str = "telegram",
    emit_events: bool = True,
    return_details: bool = False,
) -> int | ApprovalBatchResolution:
    if not isinstance(organization_id, UUID) or organization_id.int == 0:
        raise ValueError("approval_organization_required")
    async with AsyncSessionLocal() as db:
        stmt = select(ApprovalRequest).where(
            ApprovalRequest.batch_key == batch_key,
            ApprovalRequest.status == "pending",
        )
        if organization_id is not None:
            stmt = stmt.where(ApprovalRequest.organization_id == organization_id)
        rows = list(((await db.execute(stmt)).scalars()))
        approval_ids = [row.id for row in rows]

    decision_count = 0
    expired_count = 0
    for approval_id in approval_ids:
        approval = await resolve_approval_request(
            approval_id,
            decision,
            note=note,
            organization_id=organization_id,
            audit_actor_id=audit_actor_id,
            audit_source=audit_source,
            emit_events=emit_events,
        )
        if approval is None:
            continue
        if approval.status == decision:
            decision_count += 1
        elif approval.status == "expired":
            expired_count += 1
    if return_details:
        return ApprovalBatchResolution(
            decision_count=decision_count, expired_count=expired_count
        )
    return decision_count


async def resolve_approval_batch_reference(
    callback_ref: str,
    decision: str,
    note: str | None = None,
    organization_id: UUID | None = None,
    *,
    audit_actor_id: str | UUID | None = None,
    audit_source: str = "telegram",
    emit_events: bool = True,
    return_details: bool = False,
) -> int | ApprovalBatchResolution:
    if not isinstance(organization_id, UUID) or organization_id.int == 0:
        raise ValueError("approval_organization_required")
    if decision not in {"approved", "rejected"}:
        raise ValueError("approval_decision_invalid")
    if not is_approval_batch_callback_ref(callback_ref):
        raise ValueError("approval_batch_reference_invalid")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ApprovalRequest.batch_key)
            .where(
                ApprovalRequest.organization_id == organization_id,
                ApprovalRequest.status == "pending",
                ApprovalRequest.batch_key.is_not(None),
            )
            .distinct()
        )
        batch_keys = {
            key for key in result.scalars().all() if isinstance(key, str) and key
        }

    matches = {
        key for key in batch_keys if approval_batch_callback_ref(key) == callback_ref
    }
    if len(matches) != 1:
        return ApprovalBatchResolution(0, 0) if return_details else 0
    return await resolve_approval_batch(
        matches.pop(),
        decision,
        note=note,
        organization_id=organization_id,
        audit_actor_id=audit_actor_id,
        audit_source=audit_source,
        emit_events=emit_events,
        return_details=return_details,
    )


async def mark_subject_approvals_resolved(
    subject_type: str,
    subject_id: UUID,
    decision: str,
    note: str | None = None,
    *,
    auth: AuthContext | None = None,
) -> int:
    owner = _trusted_approval_owner(auth)
    async with AsyncSessionLocal() as db:
        ids = list((await db.execute(select(ApprovalRequest.id).where(
            ApprovalRequest.subject_type == subject_type,
            ApprovalRequest.subject_id == subject_id,
            ApprovalRequest.organization_id == owner,
            ApprovalRequest.status == "pending",
        ))).scalars())
    count = 0
    for approval_id in ids:
        try:
            approval = await resolve_approval_request(
                approval_id, decision, note=note, organization_id=owner,
            )
        except ApprovalAlreadyProcessedError:
            continue
        if approval is not None and approval.status == decision:
            count += 1
    return count


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
    organization_id = getattr(approval, "organization_id", None)
    if not isinstance(organization_id, UUID) or organization_id.int == 0:
        return

    try:
        async with AsyncSessionLocal() as db:
            bindings = list(
                (
                    await db.execute(
                        select(TelegramApprovalBinding).where(
                            TelegramApprovalBinding.organization_id == organization_id,
                            TelegramApprovalBinding.revoked_at.is_(None),
                        )
                    )
                ).scalars()
            )
            chat_ids = []
            for binding in bindings:
                auth = await resolve_telegram_auth_context(
                    db, binding.telegram_user_id, binding.telegram_chat_id
                )
                if auth is not None and auth.organization_id == organization_id:
                    chat_ids.append(binding.telegram_chat_id)
    except Exception as exc:
        logger.warning("Approval notification recipient lookup failed: %s", type(exc).__name__)
        return

    expires_at = approval.expires_at.isoformat() if approval.expires_at else "no expiry"
    message = (
        "Approval required\n\n"
        f"Title: {approval.title}\n"
        f"Action: {approval.action_type}\n"
        f"Requested by: {approval.requested_by or 'system'}\n"
        f"Expires: {expires_at}"
    )
    for chat_id in chat_ids:
        try:
            delivered = await send_message(
                message,
                parse_mode=None,
                reply_markup=approval_keyboard(str(approval.id), approval.batch_key),
                chat_id=chat_id,
            )
        except Exception as exc:
            logger.warning(
                "Approval notification send failed: approval_id=%s action_type=%s error=%s",
                approval.id,
                approval.action_type,
                type(exc).__name__,
            )
            continue
        if not delivered:
            logger.warning(
                "Approval notification send failed: approval_id=%s action_type=%s error=not_delivered",
                approval.id,
                approval.action_type,
            )
