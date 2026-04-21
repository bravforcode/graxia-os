from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.approval_flow import ApprovalFlowManager
from app.models.approval_request import ApprovalRequest
from app.models.submission import Submission


@pytest_asyncio.fixture()
async def approval_flow_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr("app.core.approval_flow.AsyncSessionLocal", session_factory)
    yield session_factory


@pytest.mark.asyncio
async def test_request_approval_persists_current_model_and_sends_notification(
    approval_flow_session_factory,
    monkeypatch,
):
    manager = ApprovalFlowManager()
    send_approval = AsyncMock()
    callback = AsyncMock()
    monkeypatch.setattr(manager, "_send_telegram_approval", send_approval)

    approval_id = await manager.request_approval(
        "email_send",
        "Send proposal to client",
        {"to": "client@example.com", "subject": "Proposal", "body": "Hello"},
        priority="high",
        callback=callback,
    )

    async with approval_flow_session_factory() as session:
        approval = await session.get(ApprovalRequest, UUID(approval_id))

    assert approval is not None
    assert approval.title == "Send proposal to client"
    assert approval.action_type == "email_send"
    assert approval.status == "pending"
    assert approval.policy_class == "approval_required"
    assert approval.details["priority"] == "high"
    assert approval.details["to"] == "client@example.com"
    assert approval.expires_at is not None
    assert approval_id in manager.pending_approvals
    send_approval.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_approval_executes_action_and_callback_once(
    approval_flow_session_factory,
    monkeypatch,
):
    manager = ApprovalFlowManager()
    execute_action = AsyncMock(return_value=True)
    callback = AsyncMock()
    monkeypatch.setattr(manager, "_execute_action", execute_action)

    approval = ApprovalRequest(
        title="Send email",
        action_type="email_send",
        status="pending",
        policy_class="approval_required",
        requested_by="test",
        details={"to": "client@example.com"},
        preview={},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    async with approval_flow_session_factory() as session:
        session.add(approval)
        await session.commit()
        await session.refresh(approval)

    manager.pending_approvals[str(approval.id)] = {"callback": callback, "data": approval.details}

    result = await manager.handle_approval(str(approval.id), approved=True, user_id="operator")
    duplicate_result = await manager.handle_approval(str(approval.id), approved=True, user_id="operator")

    async with approval_flow_session_factory() as session:
        stored = await session.get(ApprovalRequest, approval.id)

    assert result is True
    assert duplicate_result is False
    assert stored.status == "approved"
    assert stored.resolved_at is not None
    assert stored.resolution_note == "Resolved by operator"
    execute_action.assert_awaited_once()
    callback.assert_awaited_once_with({"to": "client@example.com"})


@pytest.mark.asyncio
async def test_handle_approval_rejects_invalid_missing_expired_and_rejected_requests(
    approval_flow_session_factory,
    monkeypatch,
):
    manager = ApprovalFlowManager()
    execute_action = AsyncMock(return_value=True)
    monkeypatch.setattr(manager, "_execute_action", execute_action)

    expired = ApprovalRequest(
        title="Expired action",
        action_type="email_send",
        status="pending",
        policy_class="approval_required",
        details={},
        preview={},
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    rejectable = ApprovalRequest(
        title="Reject action",
        action_type="email_send",
        status="pending",
        policy_class="approval_required",
        details={},
        preview={},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    async with approval_flow_session_factory() as session:
        session.add_all([expired, rejectable])
        await session.commit()
        await session.refresh(expired)
        await session.refresh(rejectable)

    assert await manager.handle_approval("not-a-uuid", approved=True) is False
    assert await manager.handle_approval("00000000-0000-0000-0000-000000000000", approved=True) is False
    assert await manager.handle_approval(str(expired.id), approved=True) is False
    assert await manager.handle_approval(str(rejectable.id), approved=False) is False

    async with approval_flow_session_factory() as session:
        expired_stored = await session.get(ApprovalRequest, expired.id)
        rejected_stored = await session.get(ApprovalRequest, rejectable.id)

    assert expired_stored.status == "expired"
    assert rejected_stored.status == "rejected"
    execute_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_expiration_reminders_pending_list_and_stats_use_real_db(
    approval_flow_session_factory,
    monkeypatch,
):
    manager = ApprovalFlowManager()
    send_reminder = AsyncMock()
    monkeypatch.setattr(manager, "_send_reminder", send_reminder)
    now = datetime.now(UTC)

    expired = ApprovalRequest(
        title="Expired",
        action_type="email_send",
        status="pending",
        policy_class="approval_required",
        details={},
        preview={},
        expires_at=now - timedelta(minutes=1),
    )
    old_pending = ApprovalRequest(
        title="Old pending",
        action_type="email_send",
        status="pending",
        policy_class="approval_required",
        details={},
        preview={},
        expires_at=now + timedelta(hours=1),
        created_at=now - timedelta(hours=13),
    )
    fresh_pending = ApprovalRequest(
        title="Fresh pending",
        action_type="email_send",
        status="pending",
        policy_class="approval_required",
        details={},
        preview={},
        expires_at=now + timedelta(hours=1),
        created_at=now,
    )
    approved = ApprovalRequest(
        title="Approved",
        action_type="email_send",
        status="approved",
        policy_class="approval_required",
        details={},
        preview={},
        resolved_at=now,
    )
    rejected = ApprovalRequest(
        title="Rejected",
        action_type="email_send",
        status="rejected",
        policy_class="approval_required",
        details={},
        preview={},
        resolved_at=now,
    )
    async with approval_flow_session_factory() as session:
        session.add_all([expired, old_pending, fresh_pending, approved, rejected])
        await session.commit()

    await manager.check_expired_approvals()
    await manager.send_reminders()
    pending = await manager.get_pending_approvals(limit=10)
    stats = await manager.get_approval_stats()

    async with approval_flow_session_factory() as session:
        expired_stored = await session.get(ApprovalRequest, expired.id)
        old_pending_stored = await session.get(ApprovalRequest, old_pending.id)

    assert expired_stored.status == "expired"
    assert old_pending_stored.details["reminder_sent_at"]
    assert {item.title for item in pending} == {"Old pending", "Fresh pending"}
    assert stats["total"] == 5
    assert stats["by_status"]["approved"] == 1
    assert stats["by_status"]["rejected"] == 1
    assert stats["approval_rate_percent"] == 50.0
    send_reminder.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_email_and_job_apply_actions_delegate_to_integrations(
    approval_flow_session_factory,
    monkeypatch,
):
    manager = ApprovalFlowManager()
    monkeypatch.setattr("app.core.google_workspace.google_workspace.send_message", AsyncMock(return_value="gmail-1"))
    monkeypatch.setattr("app.telegram_bot.bot.send_message", AsyncMock(return_value=True))
    monkeypatch.setattr("app.core.event_bus.event_bus.emit", AsyncMock())

    email_approval = ApprovalRequest(
        title="Send email",
        action_type="email_send",
        policy_class="approval_required",
        details={"to": "client@example.com", "subject": "Hello", "body": "Body"},
    )
    job_result = await manager._execute_job_apply(
        {"job_url": "https://example.test/job", "cover_letter": "Cover letter"}
    )
    email_result = await manager._execute_action(email_approval)
    missing_email_result = await manager._execute_email_send({"to": "client@example.com"})
    unknown_result = await manager._execute_action(
        ApprovalRequest(title="Unknown", action_type="unknown", policy_class="approval_required", details={})
    )

    async with approval_flow_session_factory() as session:
        submissions = list((await session.execute(select(Submission))).scalars())

    assert job_result is True
    assert email_result is True
    assert missing_email_result is False
    assert unknown_result is False
    assert len(submissions) == 1
    assert submissions[0].type == "application"
    assert submissions[0].status == "sent"
