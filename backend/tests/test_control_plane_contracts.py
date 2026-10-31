import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from app.auth.context import AuthContext
from app.core.control_plane import (
    mark_subject_approvals_resolved,
    queue_approval_request,
    resolve_approval_batch,
    resolve_approval_request,
)
from app.core.event_bus import event_bus
from app.models.approval_request import ApprovalRequest
from app.models.content_draft import ContentDraft
from sqlalchemy import select


def authenticated_owner(organization_id, actor_id="control-plane-contract-owner"):
    return AuthContext(
        actor_type="admin",
        actor_id=actor_id,
        organization_id=organization_id,
        permissions=["approvals:resolve"],
        environment="test",
        auth_method="bearer_jwt",
        is_mock_auth=False,
        is_authenticated=True,
    )


@pytest_asyncio.fixture()
async def control_plane_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr("app.core.control_plane.AsyncSessionLocal", session_factory)
    yield session_factory


@pytest_asyncio.fixture()
async def isolated_control_plane_event_bus():
    event_bus.stop()
    event_bus.reset()
    yield event_bus
    event_bus.stop()
    event_bus.reset()


@pytest.mark.asyncio
async def test_queue_and_resolve_approval_emit_lifecycle_events(
    control_plane_session_factory,
    isolated_control_plane_event_bus,
    default_org,
    monkeypatch,
):
    from app.models.telegram_pairing import TelegramApprovalBinding
    from app.models.user import User

    owner = User(
        id=uuid4(),
        email=f"control-plane-{uuid4()}@example.invalid",
        hashed_password="fixture-only",
        role="admin",
        is_active=True,
        organization_id=default_org.id,
    )
    async with control_plane_session_factory() as db:
        db.add(owner)
        await db.flush()
        db.add(
            TelegramApprovalBinding(
                organization_id=default_org.id,
                user_id=owner.id,
                telegram_user_id="778123456",
                telegram_chat_id="778123456",
            )
        )
        await db.commit()

    notify = AsyncMock(return_value=True)
    monkeypatch.setattr("app.core.control_plane.send_message", notify)

    requested: list[dict] = []
    resolved: list[dict] = []

    async def on_requested(payload: dict) -> None:
        requested.append(payload)

    async def on_resolved(payload: dict) -> None:
        resolved.append(payload)

    event_bus.subscribe("approval.requested", on_requested)
    event_bus.subscribe("approval.resolved", on_resolved)

    processor = asyncio.create_task(event_bus.start_processing())
    try:
        approval = await queue_approval_request(
            title="Approve proposal send",
            action_type="email_send",
            details={"to": "client@example.com", "subject": "Proposal"},
            preview={"summary": "Ready to send"},
            requested_by="draft_agent",
            auth=authenticated_owner(default_org.id, str(owner.id)),
        )
        await asyncio.wait_for(event_bus._queue.join(), timeout=3)

        resolved_approval = await resolve_approval_request(
            approval.id,
            "approved",
            note="Ship it",
            organization_id=default_org.id,
        )
        await asyncio.wait_for(event_bus._queue.join(), timeout=3)
    finally:
        event_bus.stop()
        processor.cancel()
        with pytest.raises(asyncio.CancelledError):
            await processor

    assert resolved_approval is not None
    assert notify.await_count == 1
    assert notify.await_args.kwargs["chat_id"] == "778123456"
    assert notify.await_args.kwargs["parse_mode"] is None
    assert len(requested) == 1
    assert len(resolved) == 1
    assert requested[0]["approval_id"] == str(approval.id)
    assert requested[0]["status"] == "pending"
    assert requested[0]["requested_by"] == "draft_agent"
    assert resolved[0]["approval_id"] == str(approval.id)
    assert resolved[0]["status"] == "approved"
    assert resolved[0]["resolution_note"] == "Ship it"
    assert event_bus.get_event_stats()["approval.requested"] == 1
    assert event_bus.get_event_stats()["approval.resolved"] == 1


@pytest.mark.asyncio
async def test_mark_subject_resolution_emits_events_for_each_pending_request(
    control_plane_session_factory,
    isolated_control_plane_event_bus,
    default_org,
):
    subject_id = uuid4()
    resolved: list[dict] = []

    async def on_resolved(payload: dict) -> None:
        resolved.append(payload)

    event_bus.subscribe("approval.resolved", on_resolved)

    async with control_plane_session_factory() as session:
        session.add_all(
            [
                ApprovalRequest(
                    organization_id=default_org.id,
                    title="First approval",
                    action_type="draft_review",
                    subject_type="content_draft",
                    subject_id=subject_id,
                    status="pending",
                    policy_class="approval_required",
                    requested_by="drafter",
                    details={},
                    preview={},
                ),
                ApprovalRequest(
                    organization_id=default_org.id,
                    title="Second approval",
                    action_type="draft_review",
                    subject_type="content_draft",
                    subject_id=subject_id,
                    status="pending",
                    policy_class="approval_required",
                    requested_by="drafter",
                    details={},
                    preview={},
                ),
                ApprovalRequest(
                    organization_id=default_org.id,
                    title="Already approved",
                    action_type="draft_review",
                    subject_type="content_draft",
                    subject_id=subject_id,
                    status="approved",
                    policy_class="approval_required",
                    requested_by="drafter",
                    details={},
                    preview={},
                ),
            ]
        )
        await session.commit()

    processor = asyncio.create_task(event_bus.start_processing())
    try:
        count = await mark_subject_approvals_resolved(
            subject_type="content_draft",
            subject_id=subject_id,
            decision="rejected",
            note="Superseded by operator",
            auth=authenticated_owner(default_org.id),
        )
        await asyncio.wait_for(event_bus._queue.join(), timeout=3)
    finally:
        event_bus.stop()
        processor.cancel()
        with pytest.raises(asyncio.CancelledError):
            await processor

    async with control_plane_session_factory() as session:
        statuses = list(
            (
                await session.execute(
                    select(ApprovalRequest.status, ApprovalRequest.resolution_note).where(
                        ApprovalRequest.subject_type == "content_draft",
                        ApprovalRequest.subject_id == subject_id,
                    )
                )
            ).all()
        )

    assert count == 2
    assert len(resolved) == 2
    assert all(payload["status"] == "rejected" for payload in resolved)
    assert all(payload["resolution_note"] == "Superseded by operator" for payload in resolved)
    assert statuses.count(("rejected", "Superseded by operator")) == 2
    assert ("approved", None) in statuses


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["approved", "rejected"])
async def test_expired_approval_is_not_counted_as_draft_decision_success(
    control_plane_session_factory,
    isolated_control_plane_event_bus,
    default_org,
    decision,
):
    subject_id = uuid4()
    expired_at = datetime.now(UTC) - timedelta(seconds=1)
    batch_key = f"expired-{uuid4()}"
    async with control_plane_session_factory() as session:
        session.add(ContentDraft(
            id=subject_id,
            organization_id=default_org.id,
            type="proposal",
            title="Expired draft review",
            content="Synthetic content",
            status="pending",
        ))
        session.add_all(
            [
                ApprovalRequest(
                    organization_id=default_org.id,
                    title="Expired batch approval",
                    action_type="draft_review",
                    subject_type="content_draft",
                    subject_id=subject_id,
                    batch_key=batch_key,
                    status="pending",
                    policy_class="approval_required",
                    details={},
                    preview={},
                    expires_at=expired_at,
                ),
                ApprovalRequest(
                    organization_id=default_org.id,
                    title="Expired subject approval",
                    action_type="draft_review",
                    subject_type="content_draft",
                    subject_id=subject_id,
                    batch_key=f"subject-{uuid4()}",
                    status="pending",
                    policy_class="approval_required",
                    details={},
                    preview={},
                    expires_at=expired_at,
                ),
            ]
        )
        await session.commit()

    batch_count = await resolve_approval_batch(
        batch_key,
        decision,
        note="Operator decision arrived too late",
        organization_id=default_org.id,
    )
    subject_count = await mark_subject_approvals_resolved(
        subject_type="content_draft",
        subject_id=subject_id,
        decision=decision,
        note="Operator decision arrived too late",
        auth=authenticated_owner(default_org.id),
    )

    async with control_plane_session_factory() as session:
        rows = list((await session.execute(select(ApprovalRequest).where(
            ApprovalRequest.subject_id == subject_id,
            ApprovalRequest.organization_id == default_org.id,
        ))).scalars())
        draft = await session.get(ContentDraft, subject_id)
    assert batch_count == 0
    assert subject_count == 0
    assert len(rows) == 2
    assert all(row.status == "expired" for row in rows)
    assert draft.status == "pending"
    assert draft.approved_at is None
    assert draft.rejection_reason is None
