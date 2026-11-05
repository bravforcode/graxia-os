"""Actual SQLite/API/Telegram code with no real notification or Gmail adapter."""
import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.core import control_plane
from app.api import approvals
from app.models.audit import AuditLog
from app.models.approval_request import ApprovalRequest
from app.models.organization import Organization
from app.models.telegram_pairing import TelegramApprovalBinding
from app.models.user import User
from app.telegram_bot import bot


def trusted(owner):
    return AuthContext(organization_id=owner, actor_id="12345", is_authenticated=True,
                       is_mock_auth=False, environment="production",
                       auth_method="bearer_jwt", permissions=["approvals:resolve"])


@pytest_asyncio.fixture
async def boundaries(session_factory, default_org, monkeypatch):
    monkeypatch.setattr(control_plane, "AsyncSessionLocal", session_factory)
    notify, events, sender = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(control_plane, "send_message", notify)
    monkeypatch.setattr(control_plane.event_bus, "emit", events)
    monkeypatch.setattr(bot.settings, "TELEGRAM_CHAT_ID", "12345")
    monkeypatch.setitem(sys.modules, "app.core.google_workspace", SimpleNamespace(
        google_workspace=SimpleNamespace(send_message=sender)))
    return session_factory, default_org.id, notify, events, sender


async def pending(boundaries, action="send_email", **changes):
    factory, owner, *_ = boundaries
    values = dict(organization_id=owner, title="Synthetic approval only",
                  action_type=action, status="pending", policy_class="approval_required",
                  details={"to": "fixture@example.invalid", "subject": "Fixture", "body": "Synthetic"},
                  preview={})
    values.update(changes)
    row = ApprovalRequest(**values)
    async with factory() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def bind_owner(boundaries, organization_id, telegram_id="12345"):
    factory, *_ = boundaries
    user = User(
        id=uuid4(),
        email=f"telegram-callback-{uuid4()}@example.invalid",
        hashed_password="fixture-only",
        role="admin",
        is_active=True,
        organization_id=organization_id,
    )
    binding = TelegramApprovalBinding(
        organization_id=organization_id,
        user_id=user.id,
        telegram_user_id=telegram_id,
        telegram_chat_id=telegram_id,
    )
    async with factory() as session:
        organization = await session.get(Organization, organization_id)
        assert organization is not None
        await session.flush()
        session.add(user)
        await session.flush()
        session.add(binding)
        await session.commit()
    return user


def callback(row, auth, chat="12345", action="approve"):
    query = SimpleNamespace(data=f"{action}:{row.id}", answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(callback_query=query, effective_chat=SimpleNamespace(id=chat, type="private"),
                             effective_user=SimpleNamespace(id="12345"))
    context = SimpleNamespace(bot_data={"approval_auth_context": auth} if auth else {})
    return update, context


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["absent", "unauthenticated", "missing_owner", "nil_owner", "mock"])
async def test_production_creation_missing_trusted_context_has_zero_writes(boundaries, kind):
    factory, owner, notify, events, sender = boundaries
    contexts = {
        "absent": None, "unauthenticated": AuthContext(organization_id=owner),
        "missing_owner": trusted(None), "nil_owner": trusted(UUID(int=0)),
        "mock": AuthContext(organization_id=owner, is_authenticated=True,
                            is_mock_auth=True, environment="production"),
    }
    with pytest.raises(ValueError, match="approval_authenticated_organization_required"):
        await control_plane.queue_approval_request(
            title="Synthetic", action_type="send_email", details={"organization_id": str(owner)},
            auth=contexts[kind],
        )
    async with factory() as session:
        assert list((await session.execute(select(ApprovalRequest))).scalars()) == []
    notify.assert_not_awaited()
    events.assert_not_awaited()
    sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_production_event_creation_uses_context_not_metadata(boundaries):
    factory, owner, *_ = boundaries
    with pytest.raises(ValueError):
        await approvals.create_approval_from_event("send_email", "Synthetic", metadata={"organization_id": str(owner)})
    row = await approvals.create_approval_from_event(
        "send_email", "Synthetic", metadata={"organization_id": str(uuid4())}, auth=trusted(owner),
    )
    async with factory() as session:
        assert (await session.get(ApprovalRequest, row.id)).organization_id == owner


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["absent", "mock", "foreign_chat", "group", "foreign_user"])
async def test_production_callback_missing_binding_changes_nothing(boundaries, kind):
    factory, owner, _, events, sender = boundaries
    row = await pending(boundaries)
    auth = trusted(owner) if kind != "absent" else None
    if kind == "mock":
        auth = AuthContext(organization_id=owner, is_authenticated=True)
    update, context = callback(row, auth, chat="999" if kind == "foreign_chat" else "12345")
    if kind == "group":
        update.effective_chat.type = "group"
    if kind == "foreign_user":
        update.effective_user.id = "999"
    await bot.approval_callback(update, context)
    async with factory() as session:
        assert (await session.get(ApprovalRequest, row.id)).status == "pending"
    events.assert_not_awaited()
    sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_production_callback_foreign_owner_changes_nothing(boundaries):
    factory, _, _, events, sender = boundaries
    row = await pending(boundaries)
    foreign_org = Organization(name="Foreign tenant", slug=f"foreign-{uuid4()}")
    async with factory() as session:
        session.add(foreign_org)
        await session.commit()
        await session.refresh(foreign_org)
    await bind_owner(boundaries, foreign_org.id)
    update, context = callback(row, trusted(foreign_org.id))
    await bot.approval_callback(update, context)
    async with factory() as session:
        assert (await session.get(ApprovalRequest, row.id)).status == "pending"
    sender.assert_not_awaited()
    events.assert_not_awaited()


@pytest.mark.asyncio
async def test_setup_bot_callback_without_trusted_binding_fails_closed(boundaries, monkeypatch):
    factory, _, _, events, sender = boundaries
    row = await pending(boundaries)
    monkeypatch.setattr(bot.settings, "TELEGRAM_BOT_TOKEN", "123456:AAprodTokenWithEnoughEntropyForValidation")
    monkeypatch.setattr(bot, "_app", None)

    application = bot.setup_bot()
    registered = [handler for handlers in application.handlers.values() for handler in handlers]
    assert any(getattr(handler, "callback", None) is bot.approval_callback for handler in registered)
    assert "approval_auth_context" not in application.bot_data
    assert any(getattr(handler, "callback", None) is bot.pair_command for handler in registered)

    update, _ = callback(row, auth=None)
    await bot.approval_callback(update, application)

    async with factory() as session:
        assert (await session.get(ApprovalRequest, row.id)).status == "pending"
    assert "verified tenant/chat binding required" in update.callback_query.edit_message_text.call_args.args[0]
    events.assert_not_awaited()
    sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_callback_rejects_forged_in_memory_auth_without_persisted_binding(boundaries):
    factory, owner, notify, events, sender = boundaries
    row = await pending(boundaries)
    update, context = callback(row, trusted(owner))

    await bot.approval_callback(update, context)

    async with factory() as session:
        assert (await session.get(ApprovalRequest, row.id)).status == "pending"
    notify.assert_not_awaited()
    events.assert_not_awaited()
    sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_production_callbacks_atomic_single_consumption(boundaries, monkeypatch, tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.models.base import Base

    _, _, _, events, sender = boundaries
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'approval-callback-race.sqlite3'}",
        connect_args={"timeout": 10},
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(control_plane, "AsyncSessionLocal", factory)
        monkeypatch.setattr(bot, "AsyncSessionLocal", factory)

        owner = uuid4()
        row = ApprovalRequest(
            organization_id=owner,
            title="Synthetic approval only",
            action_type="send_email",
            status="pending",
            policy_class="approval_required",
            details={"to": "fixture@example.invalid", "subject": "Fixture", "body": "Synthetic"},
            preview={},
        )
        user = User(
            id=uuid4(),
            email=f"telegram-race-{uuid4()}@example.invalid",
            hashed_password="fixture-only",
            role="admin",
            is_active=True,
            organization_id=owner,
        )
        async with factory() as session:
            session.add(Organization(id=owner, name="Race tenant", slug=f"race-{owner}"))
            await session.flush()
            session.add_all((user, row))
            await session.flush()
            session.add(TelegramApprovalBinding(
                organization_id=owner,
                user_id=user.id,
                telegram_user_id="12345",
                telegram_chat_id="12345",
            ))
            await session.commit()

        original_get, barrier, readers = AsyncSession.get, asyncio.Event(), 0

        async def get(session, model, identifier, *args, **kwargs):
            nonlocal readers
            result = await original_get(session, model, identifier, *args, **kwargs)
            if model is ApprovalRequest and identifier == row.id:
                readers += 1
                if readers == 2:
                    barrier.set()
                await asyncio.wait_for(barrier.wait(), 5)
            return result

        monkeypatch.setattr(AsyncSession, "get", get)
        calls = [callback(row, trusted(owner)) for _ in range(2)]
        await asyncio.wait_for(asyncio.gather(*(bot.approval_callback(*call) for call in calls)), 10)
        sender.assert_not_awaited()
        events.assert_not_awaited()
        async with factory() as session:
            final_row = await session.get(ApprovalRequest, row.id)
            final_audits = list((await session.execute(select(AuditLog).where(
                AuditLog.entity_id == row.id,
                AuditLog.event_type == "approval.resolved",
            ))).scalars())
        responses = [call[0].callback_query.edit_message_text.call_args.args[0] for call in calls]
        assert sum("Approved; action not executed; no message sent." in response
                   for response in responses) == 1, (responses, final_row.status, len(final_audits))
        assert sum("already processed" in response for response in responses) == 1
        assert final_row.status == "approved"
        assert len(final_audits) == 1
        assert final_audits[0].user_id == user.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_production_approval_fails_closed_without_central_email_api(boundaries):
    factory, owner, _, _, sender = boundaries
    await bind_owner(boundaries, owner)
    row = await pending(boundaries, details={
        "to": "fixture@example.invalid", "subject": "Fixture", "body": "Synthetic",
        "provider_receipt": "forged", "organization_id": str(uuid4()),
    })
    sender.return_value = "provider-accepted-fixture"
    update, context = callback(row, trusted(owner))
    await bot.approval_callback(update, context)
    message = update.callback_query.edit_message_text.call_args.args[0]
    assert message == "Approved; action not executed; no message sent."
    async with factory() as session:
        assert (await session.get(ApprovalRequest, row.id)).status == "approved"
    sender.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["job_application", "job_apply_submit", "linkedin_outreach"])
async def test_production_manual_or_unsupported_action_not_executed(boundaries, action):
    factory, owner, _, _, sender = boundaries
    await bind_owner(boundaries, owner)
    row = await pending(boundaries, action=action)
    update, context = callback(row, trusted(owner))
    await bot.approval_callback(update, context)
    assert "action not executed" in update.callback_query.edit_message_text.call_args.args[0]
    async with factory() as session:
        assert (await session.get(ApprovalRequest, row.id)).status == "approved"
    sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_production_api_requires_auth_and_foreign_owner_denied(boundaries):
    factory, owner, _, events, sender = boundaries
    row = await pending(boundaries)
    from fastapi import HTTPException
    async with factory() as session:
        with pytest.raises(ValueError):
            await approvals.approve_approval(row.id, db=session, auth=None)
        with pytest.raises(HTTPException) as exc:
            await approvals.approve_approval(row.id, db=session, auth=trusted(uuid4()))
        assert exc.value.status_code == 404
        approved = await approvals.approve_approval(row.id, db=session, auth=trusted(owner))
    assert approved.status == "approved"
    sender.assert_not_awaited()
    events.assert_awaited_once()
