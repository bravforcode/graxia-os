from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from types import SimpleNamespace
import sys
import asyncio
from uuid import UUID

import pytest
import pytest_asyncio
from app.core.approval_flow import ApprovalFlowManager, VerifiedJobApplicationReceipt
from app.models.approval_request import ApprovalRequest
from app.models.submission import Submission
from sqlalchemy import select


@pytest_asyncio.fixture()
async def approval_flow_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr("app.core.approval_flow.AsyncSessionLocal", session_factory)
    yield session_factory


@pytest.mark.asyncio
async def test_request_approval_persists_current_model_and_sends_notification(
    approval_flow_session_factory, default_org,
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
        organization_id=default_org.id,
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
    approval_flow_session_factory, default_org,
    monkeypatch,
):
    manager = ApprovalFlowManager()
    execute_action = AsyncMock(return_value=True)
    callback = AsyncMock()
    monkeypatch.setattr(manager, "_execute_action", execute_action)

    approval = ApprovalRequest(
        organization_id=default_org.id,
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
    duplicate_result = await manager.handle_approval(
        str(approval.id), approved=True, user_id="operator"
    )

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
    approval_flow_session_factory, default_org,
    monkeypatch,
):
    manager = ApprovalFlowManager()
    execute_action = AsyncMock(return_value=True)
    monkeypatch.setattr(manager, "_execute_action", execute_action)

    expired = ApprovalRequest(
        organization_id=default_org.id,
        title="Expired action",
        action_type="email_send",
        status="pending",
        policy_class="approval_required",
        details={},
        preview={},
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    rejectable = ApprovalRequest(
        organization_id=default_org.id,
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
    assert (
        await manager.handle_approval("00000000-0000-0000-0000-000000000000", approved=True)
        is False
    )
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
    approval_flow_session_factory, default_org,
    monkeypatch,
):
    manager = ApprovalFlowManager()
    send_reminder = AsyncMock()
    monkeypatch.setattr(manager, "_send_reminder", send_reminder)
    now = datetime.now(UTC)

    expired = ApprovalRequest(
        organization_id=default_org.id,
        title="Expired",
        action_type="email_send",
        status="pending",
        policy_class="approval_required",
        details={},
        preview={},
        expires_at=now - timedelta(minutes=1),
    )
    old_pending = ApprovalRequest(
        organization_id=default_org.id,
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
        organization_id=default_org.id,
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
        organization_id=default_org.id,
        title="Approved",
        action_type="email_send",
        status="approved",
        policy_class="approval_required",
        details={},
        preview={},
        resolved_at=now,
    )
    rejected = ApprovalRequest(
        organization_id=default_org.id,
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
async def test_job_apply_without_provider_never_claims_sent(
    approval_flow_session_factory, default_org, monkeypatch,
):
    manager = ApprovalFlowManager()
    emit = AsyncMock()
    monkeypatch.setattr("app.core.event_bus.event_bus.emit", emit)
    assert await manager._execute_job_apply({
        "organization_id": str(default_org.id),
        "job_url": "https://example.invalid/job",
        "provider_receipt": {"verified": True, "id": "forged"},
    }, organization_id=default_org.id) is False
    async with approval_flow_session_factory() as session:
        assert list((await session.execute(select(Submission))).scalars()) == []
    emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_approved_job_with_unknown_provider_outcome_is_not_sent(
    approval_flow_session_factory, default_org, monkeypatch,
):
    sender = AsyncMock(side_effect=TimeoutError("unknown outcome"))
    manager = ApprovalFlowManager(job_application_sender=sender)
    callback, emit = AsyncMock(), AsyncMock()
    monkeypatch.setattr("app.core.event_bus.event_bus.emit", emit)
    approval = ApprovalRequest(
        title="Synthetic job", action_type="job_apply", status="pending",
        organization_id=default_org.id,
        policy_class="approval_required", preview={},
        details={"organization_id": str(default_org.id)},
    )
    async with approval_flow_session_factory() as session:
        session.add(approval)
        await session.commit()
        await session.refresh(approval)
    manager.pending_approvals[str(approval.id)] = {"callback": callback}
    assert await manager.handle_approval(str(approval.id), True) is False
    async with approval_flow_session_factory() as session:
        stored = await session.get(ApprovalRequest, approval.id)
        assert stored.status == "approved"
        assert list((await session.execute(select(Submission))).scalars()) == []
    callback.assert_not_awaited()
    emit.assert_not_awaited()
    sender.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_creation_requires_explicit_trusted_owner(
    approval_flow_session_factory, default_org, monkeypatch,
):
    manager = ApprovalFlowManager()
    notify = AsyncMock()
    monkeypatch.setattr(manager, "_send_telegram_approval", notify)
    for owner in (None, "bad", UUID(int=0)):
        with pytest.raises(ValueError, match="approval_organization_required"):
            await manager.request_approval(
                "job_apply", "Synthetic", {"organization_id": str(default_org.id)},
                organization_id=owner,
            )
    async with approval_flow_session_factory() as session:
        assert list((await session.execute(select(ApprovalRequest))).scalars()) == []
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_callbacks_consume_once_and_bind_persisted_owner(
    approval_flow_session_factory, default_org, monkeypatch,
):
    from sqlalchemy.ext.asyncio import AsyncSession
    from uuid import uuid4
    foreign = uuid4()
    approval = ApprovalRequest(
        organization_id=default_org.id, title="Synthetic concurrent job",
        action_type="job_apply", status="pending", policy_class="approval_required",
        details={"organization_id": str(foreign)}, preview={},
    )
    async with approval_flow_session_factory() as session:
        session.add(approval)
        await session.commit()
        await session.refresh(approval)
    original_get = AsyncSession.get
    both_read = asyncio.Event()
    readers = 0
    async def simultaneous_get(session, model, identifier, *args, **kwargs):
        nonlocal readers
        row = await original_get(session, model, identifier, *args, **kwargs)
        if model is ApprovalRequest and identifier == approval.id:
            readers += 1
            if readers == 2:
                both_read.set()
            await asyncio.wait_for(both_read.wait(), 5)
        return row
    monkeypatch.setattr(AsyncSession, "get", simultaneous_get)
    receipt = VerifiedJobApplicationReceipt(
        organization_id=default_org.id, opportunity_id=None, provider="test_provider",
        external_reference="concurrent-fixture", sent_at=datetime.now(UTC),
    )
    sender = AsyncMock(return_value=receipt)
    emit = AsyncMock()
    monkeypatch.setattr(
        "app.core.event_bus.event_bus.emit_verified_submission_sent", emit
    )
    managers = [ApprovalFlowManager(job_application_sender=sender) for _ in range(2)]
    outcomes = await asyncio.wait_for(asyncio.gather(*(
        manager.handle_approval(str(approval.id), True) for manager in managers
    )), 10)
    assert sorted(outcomes) == [False, True]
    sender.assert_awaited_once()
    assert sender.call_args.args[0]["organization_id"] == str(default_org.id)
    async with approval_flow_session_factory() as session:
        rows = list((await session.execute(select(Submission))).scalars())
    assert len(rows) == 1
    assert rows[0].organization_id == default_org.id
    emit.assert_awaited_once_with(
        receipt=receipt,
        submission_id=rows[0].id,
        organization_id=default_org.id,
    )


@pytest.mark.asyncio
async def test_foreign_receipt_cannot_follow_forged_action_owner(
    approval_flow_session_factory, default_org, monkeypatch,
):
    from uuid import uuid4
    foreign = uuid4()
    approval = ApprovalRequest(
        organization_id=default_org.id, title="Synthetic forged owner",
        action_type="job_apply", status="pending", policy_class="approval_required",
        details={"organization_id": str(foreign)}, preview={},
    )
    async with approval_flow_session_factory() as session:
        session.add(approval)
        await session.commit()
        await session.refresh(approval)
    sender = AsyncMock(return_value=VerifiedJobApplicationReceipt(
        organization_id=foreign, opportunity_id=None, provider="test_provider",
        external_reference="foreign-fixture", sent_at=datetime.now(UTC),
    ))
    manager = ApprovalFlowManager(job_application_sender=sender)
    emit = AsyncMock()
    monkeypatch.setattr("app.core.event_bus.event_bus.emit", emit)
    assert await manager.handle_approval(str(approval.id), True) is False
    async with approval_flow_session_factory() as session:
        assert list((await session.execute(select(Submission))).scalars()) == []
        assert (await session.get(ApprovalRequest, approval.id)).status == "approved"
    assert sender.call_args.args[0]["organization_id"] == str(default_org.id)
    emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_email_and_job_apply_actions_delegate_to_integrations(
    approval_flow_session_factory,
    monkeypatch,
):
    sender = AsyncMock()
    manager = ApprovalFlowManager(job_application_sender=sender)
    monkeypatch.setitem(sys.modules, "app.core.google_workspace", SimpleNamespace(
        google_workspace=SimpleNamespace(send_message=AsyncMock(return_value="gmail-1"))))
    monkeypatch.setitem(sys.modules, "app.telegram_bot.bot", SimpleNamespace(
        send_message=AsyncMock(return_value=True)))
    monkeypatch.setattr("app.core.event_bus.event_bus.emit", AsyncMock())

    email_approval = ApprovalRequest(
        title="Send email",
        action_type="email_send",
        policy_class="approval_required",
        details={"to": "client@example.com", "subject": "Hello", "body": "Body"},
    )
    from app.models.organization import Organization
    from uuid import uuid4 as _new_uuid
    async with approval_flow_session_factory() as approval_session:
        org = Organization(
            id=_new_uuid(),
            name="Test Org",
            slug="test-org",
            status="active",
        )
        approval_session.add(org)
        await approval_session.commit()

    sender.return_value = VerifiedJobApplicationReceipt(
        organization_id=org.id, opportunity_id=None, provider="test_provider",
        external_reference="verified-fixture-1", sent_at=datetime.now(UTC),
    )
    job_result = await manager._execute_job_apply(
        {
            "job_url": "https://example.test/job",
            "cover_letter": "Cover letter",
            "organization_id": str(org.id),
        }, organization_id=org.id,
    )
    email_result = await manager._execute_action(email_approval)
    missing_email_result = await manager._execute_email_send({"to": "client@example.com"})
    unknown_result = await manager._execute_action(
        ApprovalRequest(
            title="Unknown", action_type="unknown", policy_class="approval_required", details={}
        )
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
    assert "verified-fixture-1" in submissions[0].outcome_notes
    sender.assert_awaited_once()
