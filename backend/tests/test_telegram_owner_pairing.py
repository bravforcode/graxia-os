"""Telegram pairing is tenant-bound and never executes approved actions."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select

from app.api import approvals
from app.api.telegram_pairing import create_pairing_challenge, revoke_pairing
from app.auth.context import AuthContext
from app.core import control_plane
from app.models.audit import AuditLog
from app.models.approval_request import ApprovalRequest
from app.models.content_draft import ContentDraft
from app.models.organization import Organization
from app.models.telegram_pairing import (
    TelegramApprovalBinding,
    TelegramPairingChallenge,
)
from app.models.user import User
from app.services.telegram_pairing import consume_pairing_code
from app.telegram_bot import bot


def trusted(user: User, *, organization_id=None) -> AuthContext:
    return AuthContext(
        organization_id=organization_id or user.organization_id,
        actor_id=str(user.id),
        permissions=["approvals:resolve"],
        environment="production",
        auth_method="bearer_jwt",
        is_mock_auth=False,
        is_authenticated=True,
    )


@pytest_asyncio.fixture
async def identity(session_factory, default_org) -> User:
    user = User(
        id=uuid4(),
        email=f"telegram-owner-{uuid4()}@example.invalid",
        hashed_password="fixture-only",
        full_name="Telegram Owner",
        role="admin",
        is_active=True,
        organization_id=default_org.id,
    )
    async with session_factory() as db:
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def runtime(session_factory, monkeypatch):
    monkeypatch.setattr(bot, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(control_plane, "AsyncSessionLocal", session_factory)
    notify = AsyncMock()
    events = AsyncMock()
    monkeypatch.setattr(control_plane, "send_message", notify)
    monkeypatch.setattr(control_plane.event_bus, "emit", events)
    monkeypatch.setattr(bot, "_app", None)
    return session_factory, notify, events


def pair_update(code: str, *, telegram_id=123456789, chat_id=None, chat_type="private"):
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=telegram_id),
        effective_chat=SimpleNamespace(
            id=telegram_id if chat_id is None else chat_id,
            type=chat_type,
        ),
        effective_message=message,
    )
    return update, SimpleNamespace(args=[code])


def approval_update(
    approval_id,
    *,
    action="approve",
    telegram_id=123456789,
    chat_id=None,
    chat_type="private",
):
    query = SimpleNamespace(
        data=f"{action}:{approval_id}",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=telegram_id),
        effective_chat=SimpleNamespace(
            id=telegram_id if chat_id is None else chat_id,
            type=chat_type,
        ),
    )
    return update, SimpleNamespace(bot_data={"approval_auth_context": trusted_fixture_context()})


def approval_keyboard_update(approval_id, *, action="approve", batch_key=None):
    from app.telegram_bot.keyboards import approval_keyboard

    update, context = approval_update(approval_id, action=action)
    keyboard = approval_keyboard(str(approval_id), batch_key)
    button_index = 0 if action == "approve" else 1
    row_index = 1 if batch_key else 0
    update.callback_query.data = keyboard.inline_keyboard[row_index][button_index].callback_data
    return update, context


def read_command_update(*, telegram_id=123456789, chat_id=None, chat_type="private"):
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=telegram_id),
        effective_chat=SimpleNamespace(
            id=telegram_id if chat_id is None else chat_id,
            type=chat_type,
        ),
        effective_message=message,
        message=message,
    )
    context = SimpleNamespace(bot_data={"approval_auth_context": trusted_fixture_context()})
    return update, context, message


def trusted_fixture_context():
    """A forged in-memory context must never authorize a Telegram callback."""
    return AuthContext(
        organization_id=uuid4(),
        actor_id="123456789",
        permissions=["approvals:resolve"],
        environment="production",
        auth_method="bearer_jwt",
        is_mock_auth=False,
        is_authenticated=True,
    )


async def create_code(session_factory, user: User) -> str:
    async with session_factory() as db:
        result = await create_pairing_challenge(db=db, auth=trusted(user))
        return result.pairing_code


async def pair_code(code: str, *, telegram_id=123456789, chat_id=None, chat_type="private"):
    update, context = pair_update(
        code,
        telegram_id=telegram_id,
        chat_id=chat_id,
        chat_type=chat_type,
    )
    await bot.pair_command(update, context)
    return update


async def make_approval(
    session_factory, organization_id, *, batch_key=None, expires_at=None
):
    row = ApprovalRequest(
        organization_id=organization_id,
        title="Synthetic approval",
        action_type="send_email",
        status="pending",
        policy_class="approval_required",
        batch_key=batch_key,
        expires_at=expires_at,
        details={"to": "fixture@example.invalid", "subject": "Fixture", "body": "Synthetic"},
        preview={},
    )
    async with session_factory() as db:
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def make_draft_approval(session_factory, organization_id, *, batch_key=None):
    draft = ContentDraft(
        id=uuid4(),
        organization_id=organization_id,
        type="proposal",
        title="Synthetic draft",
        content="Synthetic content",
        status="pending",
    )
    approval = ApprovalRequest(
        organization_id=organization_id,
        title="Synthetic draft review",
        action_type="draft_review",
        subject_type="content_draft",
        subject_id=draft.id,
        batch_key=batch_key,
        status="pending",
        policy_class="approval_required",
        details={},
        preview={},
    )
    async with session_factory() as db:
        db.add_all((draft, approval))
        await db.commit()
        await db.refresh(draft)
        await db.refresh(approval)
    return draft, approval


@pytest.mark.asyncio
async def test_pairing_challenge_returns_once_stores_only_hash_and_binds_persisted_owner(
    session_factory, identity
):
    async with session_factory() as db:
        response = await create_pairing_challenge(db=db, auth=trusted(identity))

    assert response.expires_at > datetime.now(UTC)
    async with session_factory() as db:
        challenge = (await db.execute(select(TelegramPairingChallenge))).scalar_one()
        assert challenge.user_id == identity.id
        assert challenge.organization_id == identity.organization_id
        assert challenge.token_hash != response.pairing_code
        assert len(challenge.token_hash) == 64
        assert challenge.consumed_at is None
        assert challenge.revoked_at is None


@pytest.mark.asyncio
async def test_challenge_requires_real_persisted_owner_permission_and_matching_tenant(
    session_factory, identity
):
    async with session_factory() as db:
        with pytest.raises(HTTPException) as missing:
            await create_pairing_challenge(db=db, auth=None)
        assert missing.value.status_code in {401, 403}

    async with session_factory() as db:
        with pytest.raises(HTTPException) as mismatch:
            await create_pairing_challenge(
                db=db, auth=trusted(identity, organization_id=uuid4())
            )
        assert mismatch.value.status_code == 403

    async with session_factory() as db:
        stored_user = await db.get(User, identity.id)
        stored_user.role = "viewer"
        await db.commit()
    async with session_factory() as db:
        with pytest.raises(HTTPException) as denied:
            await create_pairing_challenge(db=db, auth=trusted(identity))
        assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_private_pairing_is_one_time_and_wrong_chat_does_not_consume(
    session_factory, identity, runtime
):
    code = await create_code(session_factory, identity)
    wrong = await pair_code(code, telegram_id=123456789, chat_id=987654321)
    wrong.effective_message.reply_text.assert_not_awaited()
    async with session_factory() as db:
        challenge = (await db.execute(select(TelegramPairingChallenge))).scalar_one()
        assert challenge.consumed_at is None

    paired = await pair_code(code)
    paired.effective_message.reply_text.assert_awaited_once()
    replay = await pair_code(code)
    replay.effective_message.reply_text.assert_awaited_once()
    async with session_factory() as db:
        challenge = (await db.execute(select(TelegramPairingChallenge))).scalar_one()
        bindings = list((await db.execute(select(TelegramApprovalBinding))).scalars())
        assert challenge.consumed_at is not None
        assert len(bindings) == 1
        assert bindings[0].user_id == identity.id
        assert bindings[0].organization_id == identity.organization_id
        assert bindings[0].telegram_user_id == "123456789"
        assert bindings[0].telegram_chat_id == "123456789"


@pytest.mark.asyncio
async def test_revoking_unredeemed_challenge_prevents_pairing(
    session_factory, identity, runtime
):
    code = await create_code(session_factory, identity)

    async with session_factory() as db:
        result = await revoke_pairing(db=db, auth=trusted(identity))
        assert result.status == "not_bound"
        challenge = (await db.execute(select(TelegramPairingChallenge))).scalar_one()
        assert challenge.revoked_at is not None
        assert challenge.consumed_at is None

    rejected = await pair_code(code)
    rejected.effective_message.reply_text.assert_awaited_once_with(
        "Pairing code invalid, expired, used, or no longer authorized."
    )
    async with session_factory() as db:
        challenge = (await db.execute(select(TelegramPairingChallenge))).scalar_one()
        active_bindings = list((await db.execute(select(TelegramApprovalBinding).where(
            TelegramApprovalBinding.revoked_at.is_(None)
        ))).scalars())
        assert challenge.revoked_at is not None
        assert challenge.consumed_at is None
        assert active_bindings == []


@pytest.mark.asyncio
async def test_pairing_service_consumes_valid_private_code(session_factory, identity):
    code = await create_code(session_factory, identity)
    async with session_factory() as db:
        assert await consume_pairing_code(db, code, "123456789", "123456789")


@pytest.mark.asyncio
async def test_concurrent_pairing_redemption_creates_exactly_one_binding(
    tmp_path, monkeypatch
):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.models.base import Base

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'telegram-pair-race.sqlite3'}",
        connect_args={"timeout": 10},
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        organization_id = uuid4()
        user = User(
            id=uuid4(),
            email=f"telegram-race-{uuid4()}@example.invalid",
            hashed_password="fixture-only",
            role="admin",
            is_active=True,
            organization_id=organization_id,
        )
        async with factory() as db:
            db.add(Organization(
                id=organization_id,
                name="Pairing race tenant",
                slug=f"pair-race-{organization_id}",
            ))
            await db.flush()
            db.add(user)
            await db.commit()
        code = await create_code(factory, user)

        original_execute = AsyncSession.execute
        readers = 0
        barrier = asyncio.Event()

        async def execute(session, statement, *args, **kwargs):
            nonlocal readers
            result = await original_execute(session, statement, *args, **kwargs)
            is_challenge_select = any(
                column.get("entity") is TelegramPairingChallenge
                for column in getattr(statement, "column_descriptions", [])
            )
            if is_challenge_select:
                readers += 1
                if readers == 2:
                    barrier.set()
                await asyncio.wait_for(barrier.wait(), timeout=5)
            return result

        monkeypatch.setattr(AsyncSession, "execute", execute)

        async def redeem():
            async with factory() as db:
                return await consume_pairing_code(db, code, "123456789", "123456789")

        results = await asyncio.wait_for(
            asyncio.gather(redeem(), redeem()), timeout=10
        )
        assert sorted(results) == [False, True]

        async with factory() as db:
            challenge = (await db.execute(select(TelegramPairingChallenge))).scalar_one()
            active_bindings = list((await db.execute(select(TelegramApprovalBinding).where(
                TelegramApprovalBinding.revoked_at.is_(None)
            ))).scalars())
            assert challenge.consumed_at is not None
            assert len(active_bindings) == 1
            assert active_bindings[0].user_id == user.id
            assert active_bindings[0].organization_id == organization_id
            assert active_bindings[0].telegram_user_id == "123456789"
            assert active_bindings[0].telegram_chat_id == "123456789"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_pairing_redemption_and_revoke_terminate_safely(tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.models.base import Base

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'telegram-pair-revoke-race.sqlite3'}",
        connect_args={"timeout": 10},
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        organization_id = uuid4()
        user = User(
            id=uuid4(),
            email=f"telegram-revoke-race-{uuid4()}@example.invalid",
            hashed_password="fixture-only",
            role="admin",
            is_active=True,
            organization_id=organization_id,
        )
        async with factory() as db:
            db.add(Organization(
                id=organization_id,
                name="Pairing revoke race tenant",
                slug=f"pair-revoke-race-{organization_id}",
            ))
            await db.flush()
            db.add(user)
            await db.commit()
        code = await create_code(factory, user)

        async def redeem():
            async with factory() as db:
                return await consume_pairing_code(db, code, "123456789", "123456789")

        async def revoke():
            async with factory() as db:
                return await revoke_pairing(db=db, auth=trusted(user))

        paired, revoked = await asyncio.wait_for(
            asyncio.gather(redeem(), revoke()), timeout=10
        )
        assert isinstance(paired, bool)
        assert revoked.status in {"revoked", "not_bound"}

        async with factory() as db:
            challenge = (await db.execute(select(TelegramPairingChallenge))).scalar_one()
            active_bindings = list((await db.execute(select(TelegramApprovalBinding).where(
                TelegramApprovalBinding.revoked_at.is_(None)
            ))).scalars())
        assert challenge.consumed_at is not None or challenge.revoked_at is not None
        if challenge.consumed_at is None:
            assert challenge.revoked_at is not None
        assert active_bindings == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_group_expired_revoked_and_deactivated_pairing_fail_closed(
    session_factory, identity, runtime
):
    group_code = await create_code(session_factory, identity)
    group = await pair_code(group_code, chat_type="group", chat_id=-1001)
    group.effective_message.reply_text.assert_not_awaited()
    async with session_factory() as db:
        import hashlib

        group_hash = hashlib.sha256(group_code.encode("ascii")).hexdigest()
        group_challenge = (await db.execute(select(TelegramPairingChallenge).where(
            TelegramPairingChallenge.token_hash == group_hash
        ))).scalar_one()
        assert group_challenge.consumed_at is None
        group_challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    expired = await pair_code(group_code, telegram_id=123456790)
    expired.effective_message.reply_text.assert_awaited_once()
    async with session_factory() as db:
        assert list((await db.execute(select(TelegramApprovalBinding))).scalars()) == []

    revoked_code = await create_code(session_factory, identity)
    await pair_code(revoked_code)
    async with session_factory() as db:
        result = await revoke_pairing(db=db, auth=trusted(identity))
        assert result.status == "revoked"
        binding = (await db.execute(select(TelegramApprovalBinding))).scalar_one()
        assert binding.revoked_at is not None

    inactive_code = await create_code(session_factory, identity)
    async with session_factory() as db:
        stored_user = await db.get(User, identity.id)
        stored_user.is_active = False
        await db.commit()
    inactive = await pair_code(inactive_code, telegram_id=123456790)
    inactive.effective_message.reply_text.assert_awaited_once()
    async with session_factory() as db:
        challenge = (
            await db.execute(select(TelegramPairingChallenge).where(
                TelegramPairingChallenge.revoked_at.is_(None),
                TelegramPairingChallenge.consumed_at.is_(None),
            ))
        ).scalar_one()
        assert challenge.user_id == identity.id
        assert challenge.consumed_at is None
        assert list((await db.execute(select(TelegramApprovalBinding).where(
            TelegramApprovalBinding.revoked_at.is_(None)
        ))).scalars()) == []


@pytest.mark.asyncio
async def test_callback_uses_current_database_binding_scope_and_never_executes(
    session_factory, identity, runtime, monkeypatch
):
    code = await create_code(session_factory, identity)
    await pair_code(code)
    approval = await make_approval(session_factory, identity.organization_id)
    executor = AsyncMock(return_value=True)
    monkeypatch.setattr(bot, "_execute_approved_action", executor)
    update, context = approval_update(approval.id)
    await bot.approval_callback(update, context)

    async with session_factory() as db:
        stored = await db.get(ApprovalRequest, approval.id)
        assert stored.status == "approved"
        assert stored.organization_id == identity.organization_id
    assert update.callback_query.edit_message_text.call_args.args[0] == (
        "Approved; action not executed; no message sent."
    )
    executor.assert_not_awaited()
    runtime[1].assert_not_awaited()
    runtime[2].assert_not_awaited()
    async with session_factory() as db:
        audit = (await db.execute(select(AuditLog).where(
            AuditLog.entity_id == approval.id,
            AuditLog.event_type == "approval.resolved",
        ))).scalar_one()
        assert audit.user_id == identity.id
        assert audit.metadata_json["organization_id"] == str(identity.organization_id)
        assert audit.metadata_json["decision"] == "approved"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected_status"),
    [("approve", "approved"), ("reject", "rejected")],
)
async def test_callback_updates_linked_draft_without_events_or_sends(
    session_factory, identity, runtime, monkeypatch, action, expected_status
):
    code = await create_code(session_factory, identity)
    await pair_code(code)
    draft, approval = await make_draft_approval(session_factory, identity.organization_id)
    executor = AsyncMock(return_value=True)
    monkeypatch.setattr(bot, "_execute_approved_action", executor)
    update, context = approval_update(approval.id, action=action)

    await bot.approval_callback(update, context)

    runtime[2].assert_not_awaited()
    runtime[1].assert_not_awaited()
    async with session_factory() as db:
        stored_approval = await db.get(ApprovalRequest, approval.id)
        stored_draft = await db.get(ContentDraft, draft.id)
        assert stored_approval.status == expected_status
        assert stored_draft.status == expected_status
        if action == "approve":
            assert stored_draft.approved_at is not None
            assert stored_draft.rejection_reason is None
        else:
            assert stored_draft.approved_at is None
            assert stored_draft.rejection_reason == f"Via Telegram owner {identity.id}"
    expected_message = (
        "Approved; action not executed; no message sent."
        if action == "approve"
        else "Decision: rejected; no action executed."
    )
    assert update.callback_query.edit_message_text.call_args.args[0] == expected_message
    executor.assert_not_awaited()
    runtime[1].assert_not_awaited()
    runtime[2].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected_status"),
    [("approve", "approved"), ("reject", "rejected")],
)
async def test_callback_accepts_real_approval_keyboard_payloads(
    session_factory, identity, runtime, action, expected_status
):
    code = await create_code(session_factory, identity)
    await pair_code(code)
    approval = await make_approval(session_factory, identity.organization_id)
    update, context = approval_keyboard_update(approval.id, action=action)

    await bot.approval_callback(update, context)

    async with session_factory() as db:
        stored = await db.get(ApprovalRequest, approval.id)
        assert stored.status == expected_status
        assert stored.organization_id == identity.organization_id
    expected_message = (
        "Approved; action not executed; no message sent."
        if action == "approve"
        else "Decision: rejected; no action executed."
    )
    assert update.callback_query.edit_message_text.call_args.args[0] == expected_message
    runtime[1].assert_not_awaited()
    runtime[2].assert_not_awaited()


@pytest.mark.asyncio
async def test_real_keyboard_payload_keeps_persisted_auth_and_tenant_guards(
    session_factory, identity, runtime
):
    code = await create_code(session_factory, identity)
    await pair_code(code)
    foreign_org = Organization(
        name="Foreign Keyboard Tenant",
        slug=f"foreign-keyboard-{uuid4()}",
        status="active",
    )
    async with session_factory() as db:
        db.add(foreign_org)
        await db.commit()
    approval = await make_approval(session_factory, foreign_org.id)

    wrong_tenant, context = approval_keyboard_update(approval.id)
    await bot.approval_callback(wrong_tenant, context)
    assert wrong_tenant.callback_query.edit_message_text.call_args.args[0] == (
        "Approval not found for this organization."
    )
    async with session_factory() as db:
        assert (await db.get(ApprovalRequest, approval.id)).status == "pending"
        binding = (await db.execute(select(TelegramApprovalBinding))).scalar_one()
        binding.revoked_at = datetime.now(UTC)
        await db.commit()

    revoked, revoked_context = approval_keyboard_update(approval.id)
    await bot.approval_callback(revoked, revoked_context)
    assert revoked.callback_query.edit_message_text.call_args.args[0] == (
        "Approval unavailable: verified tenant/chat binding required."
    )
    async with session_factory() as db:
        assert (await db.get(ApprovalRequest, approval.id)).status == "pending"
    runtime[1].assert_not_awaited()
    runtime[2].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected_status"),
    [("approve", "approved"), ("reject", "rejected")],
)
async def test_batch_keyboard_payload_resolves_only_current_tenant_batch(
    session_factory, identity, runtime, action, expected_status
):
    code = await create_code(session_factory, identity)
    await pair_code(code)
    foreign_org = Organization(
        name="Foreign Batch Tenant",
        slug=f"foreign-batch-{uuid4()}",
        status="active",
    )
    async with session_factory() as db:
        db.add(foreign_org)
        await db.commit()

    batch_key = "send_email:email_thread:" + ("顧客" * 80)
    first = await make_approval(
        session_factory, identity.organization_id, batch_key=batch_key
    )
    second = await make_approval(
        session_factory, identity.organization_id, batch_key=batch_key
    )
    foreign = await make_approval(session_factory, foreign_org.id, batch_key=batch_key)
    update, context = approval_keyboard_update(
        first.id, action=action, batch_key=batch_key
    )
    assert len(update.callback_query.data.encode("utf-8")) <= 64

    await bot.approval_callback(update, context)

    async with session_factory() as db:
        assert (await db.get(ApprovalRequest, first.id)).status == expected_status
        assert (await db.get(ApprovalRequest, second.id)).status == expected_status
        assert (await db.get(ApprovalRequest, foreign.id)).status == "pending"
    expected_word = "Approved" if action == "approve" else "Rejected"
    assert update.callback_query.edit_message_text.call_args.args[0] == (
        f"{expected_word} 2 approvals; no action executed."
    )
    runtime[1].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("batch_case", "expected_statuses", "expected_message"),
    [
        (
            "all_expired",
            ["expired", "expired"],
            "No approvals were approved; 2 expired; no action executed.",
        ),
        (
            "mixed",
            ["expired", "approved"],
            "Approved 1 approval; 1 expired; no action executed.",
        ),
    ],
)
async def test_telegram_batch_summary_reports_expired_rows(
    session_factory, identity, runtime, batch_case, expected_statuses, expected_message
):
    code = await create_code(session_factory, identity)
    await pair_code(code)
    batch_key = f"send_email:email_thread:{uuid4()}"
    expired_at = datetime.now(UTC) - timedelta(seconds=1)
    approvals_in_batch = []
    for index in range(2):
        row_expired = batch_case == "all_expired" or index == 0
        approvals_in_batch.append(await make_approval(
            session_factory,
            identity.organization_id,
            batch_key=batch_key,
            expires_at=expired_at if row_expired else datetime.now(UTC) + timedelta(hours=1),
        ))
    update, context = approval_keyboard_update(
        approvals_in_batch[0].id, action="approve", batch_key=batch_key
    )

    await bot.approval_callback(update, context)

    async with session_factory() as db:
        statuses = [
            (await db.get(ApprovalRequest, approval.id)).status
            for approval in approvals_in_batch
        ]
    assert statuses == expected_statuses
    assert update.callback_query.edit_message_text.call_args.args[0] == expected_message
    runtime[2].assert_not_awaited()
    runtime[1].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload_style", ["compact", "legacy"])
async def test_telegram_batch_draft_resolution_audits_actor_without_emitting_events(
    session_factory, identity, runtime, payload_style
):
    code = await create_code(session_factory, identity)
    await pair_code(code)
    batch_key = f"draft_review:content_draft:{uuid4()}"
    draft, approval = await make_draft_approval(
        session_factory, identity.organization_id, batch_key=batch_key
    )
    update, context = approval_keyboard_update(
        approval.id, action="approve", batch_key=batch_key
    )
    if payload_style == "legacy":
        update.callback_query.data = f"approvalbatch:approve:{batch_key}"

    await bot.approval_callback(update, context)

    runtime[2].assert_not_awaited()
    runtime[1].assert_not_awaited()
    async with session_factory() as db:
        stored_approval = await db.get(ApprovalRequest, approval.id)
        stored_draft = await db.get(ContentDraft, draft.id)
        audit = (await db.execute(select(AuditLog).where(
            AuditLog.entity_id == approval.id,
            AuditLog.event_type == "approval.resolved",
        ))).scalar_one()
    assert stored_approval.status == "approved"
    assert stored_draft.status == "approved"
    assert audit.user_id == identity.id
    assert audit.action == "approval.approved"
    assert audit.metadata_json["actor_id"] == str(identity.id)
    assert audit.metadata_json["organization_id"] == str(identity.organization_id)
    assert audit.metadata_json["channel"] == "telegram"
    assert audit.metadata_json["decision"] == "approved"
    assert audit.details["actor_id"] == str(identity.id)
    assert audit.triggered_by == "telegram"


def test_approval_keyboard_batch_callbacks_fit_telegram_utf8_limit():
    from app.telegram_bot.keyboards import approval_keyboard

    batch_key = "send_email:email_thread:" + ("顧客" * 80)
    keyboard = approval_keyboard(str(uuid4()), batch_key)
    callback_data = [button.callback_data for button in keyboard.inline_keyboard[1]]

    assert len(batch_key) <= 200
    assert len(batch_key.encode("utf-8")) > 64
    assert all(len(data.encode("utf-8")) <= 64 for data in callback_data)
    assert all(batch_key not in data for data in callback_data)


@pytest.mark.asyncio
async def test_batch_reference_resolution_rejects_malformed_and_ambiguous_refs(
    session_factory, identity, runtime, monkeypatch
):
    from app.core import control_plane

    collision_ref = "A" * 43
    first_key = f"send_email:email_thread:{uuid4()}"
    second_key = f"send_email:email_thread:{uuid4()}"
    first = await make_approval(
        session_factory, identity.organization_id, batch_key=first_key
    )
    second = await make_approval(
        session_factory, identity.organization_id, batch_key=second_key
    )
    monkeypatch.setattr(
        control_plane, "approval_batch_callback_ref", lambda _batch_key: collision_ref
    )
    resolver = AsyncMock(return_value=1)
    monkeypatch.setattr(control_plane, "resolve_approval_batch", resolver)

    with pytest.raises(ValueError, match="approval_batch_reference_invalid"):
        await control_plane.resolve_approval_batch_reference(
            "malformed", "approved", organization_id=identity.organization_id
        )
    count = await control_plane.resolve_approval_batch_reference(
        collision_ref, "approved", organization_id=identity.organization_id
    )

    assert count == 0
    resolver.assert_not_awaited()
    async with session_factory() as db:
        assert (await db.get(ApprovalRequest, first.id)).status == "pending"
        assert (await db.get(ApprovalRequest, second.id)).status == "pending"


@pytest.mark.asyncio
async def test_batch_callback_rejects_malformed_compact_reference(
    session_factory, identity, runtime, monkeypatch
):
    code = await create_code(session_factory, identity)
    await pair_code(code)
    approval = await make_approval(
        session_factory,
        identity.organization_id,
        batch_key=f"send_email:email_thread:{uuid4()}",
    )
    resolver = AsyncMock(return_value=1)
    monkeypatch.setattr(control_plane, "resolve_approval_batch_reference", resolver)
    update, context = approval_keyboard_update(
        approval.id,
        action="approve",
        batch_key=f"send_email:email_thread:{uuid4()}",
    )
    update.callback_query.data = "approvalbatch:a:malformed"

    await bot.approval_callback(update, context)

    resolver.assert_not_awaited()
    assert update.callback_query.edit_message_text.call_args.args[0] == (
        "Approval outcome unverified; no automatic retry."
    )
    async with session_factory() as db:
        assert (await db.get(ApprovalRequest, approval.id)).status == "pending"


@pytest.mark.asyncio
async def test_batch_keyboard_payload_requires_approval_permission_before_resolving(
    session_factory, identity, runtime, monkeypatch
):
    from app.core import control_plane

    telegram_id = "777123455"
    batch_key = f"send_email:email_thread:{uuid4()}"
    approval = await make_approval(
        session_factory, identity.organization_id, batch_key=batch_key
    )
    async with session_factory() as db:
        user = await db.get(User, identity.id)
        user.role = "user"
        db.add(
            TelegramApprovalBinding(
                organization_id=identity.organization_id,
                user_id=identity.id,
                telegram_user_id=telegram_id,
                telegram_chat_id=telegram_id,
            )
        )
        await db.commit()

    resolver = AsyncMock(return_value=1)
    reference_resolver = AsyncMock(return_value=1)
    monkeypatch.setattr(control_plane, "resolve_approval_batch", resolver)
    monkeypatch.setattr(
        control_plane, "resolve_approval_batch_reference", reference_resolver
    )
    update, context = approval_keyboard_update(
        approval.id,
        action="approve",
        batch_key=batch_key,
    )
    update.effective_user.id = int(telegram_id)
    update.effective_chat.id = int(telegram_id)

    await bot.approval_callback(update, context)

    resolver.assert_not_awaited()
    reference_resolver.assert_not_awaited()
    assert update.callback_query.edit_message_text.call_args.args[0] == (
        "Approval unavailable: verified tenant/chat binding required."
    )
    async with session_factory() as db:
        assert (await db.get(ApprovalRequest, approval.id)).status == "pending"


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_telegram_approval(
    session_factory, identity, runtime, monkeypatch
):
    code = await create_code(session_factory, identity)
    await pair_code(code)
    approval = await make_approval(session_factory, identity.organization_id)
    monkeypatch.setattr(
        control_plane,
        "log_audit_event",
        AsyncMock(side_effect=RuntimeError("audit storage unavailable")),
    )
    update, context = approval_update(approval.id)

    await bot.approval_callback(update, context)

    async with session_factory() as db:
        assert (await db.get(ApprovalRequest, approval.id)).status == "pending"
        assert list((await db.execute(select(AuditLog).where(
            AuditLog.entity_id == approval.id,
            AuditLog.event_type == "approval.resolved",
        ))).scalars()) == []
    assert "outcome unverified" in update.callback_query.edit_message_text.call_args.args[0]
    runtime[1].assert_not_awaited()
    runtime[2].assert_not_awaited()


@pytest.mark.asyncio
async def test_default_authenticated_api_resolver_still_emits_resolution_event(
    session_factory, identity, runtime
):
    approval = await make_approval(session_factory, identity.organization_id)
    async with session_factory() as db:
        result = await approvals.approve_approval(
            approval.id,
            db=db,
            auth=trusted(identity),
        )

    assert result.status == "approved"
    runtime[2].assert_awaited_once()
    event_name, payload = runtime[2].await_args.args
    assert event_name == "approval.resolved"
    assert payload["approval_id"] == str(approval.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_action", "expected_events"),
    [
        ("approved", "approval.approved", ["approval.resolved", "draft.approved"]),
        ("rejected", "approval.rejected", ["approval.resolved"]),
    ],
)
async def test_api_batch_keeps_default_events_and_audits_actor(
    session_factory, identity, runtime, decision, expected_action, expected_events
):
    batch_key = f"draft_review:content_draft:{uuid4()}"
    draft, approval = await make_draft_approval(
        session_factory, identity.organization_id, batch_key=batch_key
    )
    resolve = approvals.approve_batch if decision == "approved" else approvals.reject_batch

    result = await resolve(batch_key, auth=trusted(identity))

    assert result.count == 1
    assert result.status == decision
    event_names = [call.args[0] for call in runtime[2].await_args_list]
    assert event_names == expected_events
    async with session_factory() as db:
        stored_draft = await db.get(ContentDraft, draft.id)
        audit = (await db.execute(select(AuditLog).where(
            AuditLog.entity_id == approval.id,
            AuditLog.event_type == "approval.resolved",
        ))).scalar_one()
    assert stored_draft.status == decision
    assert audit.user_id == identity.id
    assert audit.action == expected_action
    assert audit.metadata_json["actor_id"] == str(identity.id)
    assert audit.metadata_json["organization_id"] == str(identity.organization_id)
    assert audit.metadata_json["channel"] == "api"
    assert audit.metadata_json["decision"] == decision
    assert audit.details["actor_id"] == str(identity.id)
    assert audit.triggered_by == "api"


@pytest.mark.asyncio
async def test_api_batch_keeps_non_uuid_local_actor_in_audit_metadata(
    session_factory, identity, runtime
):
    batch_key = f"send_email:email_thread:{uuid4()}"
    approval = await make_approval(
        session_factory, identity.organization_id, batch_key=batch_key
    )
    local_auth = AuthContext(
        organization_id=identity.organization_id,
        actor_id="local-dev",
        permissions=["approvals:resolve"],
        environment="local",
        auth_method="local_dev",
        is_mock_auth=True,
        is_authenticated=True,
    )

    result = await approvals.approve_batch(batch_key, auth=local_auth)

    assert result.count == 1
    async with session_factory() as db:
        audit = (await db.execute(select(AuditLog).where(
            AuditLog.entity_id == approval.id,
            AuditLog.event_type == "approval.resolved",
        ))).scalar_one()
    assert audit.user_id is None
    assert audit.metadata_json["actor_id"] == "local-dev"
    assert audit.metadata_json["channel"] == "api"
    assert audit.details["actor_id"] == "local-dev"
    assert audit.triggered_by == "api"


@pytest.mark.asyncio
async def test_callback_wrong_tenant_chat_revoked_role_and_deactivation_stay_pending(
    session_factory, identity, runtime
):
    code = await create_code(session_factory, identity)
    await pair_code(code)
    approval = await make_approval(session_factory, identity.organization_id)

    wrong_chat, wrong_context = approval_update(approval.id, chat_id=987654321)
    await bot.approval_callback(wrong_chat, wrong_context)
    wrong_user, wrong_user_context = approval_update(approval.id, telegram_id=7654321)
    await bot.approval_callback(wrong_user, wrong_user_context)
    group, group_context = approval_update(approval.id, chat_type="group", chat_id=-1001)
    await bot.approval_callback(group, group_context)
    async with session_factory() as db:
        assert (await db.get(ApprovalRequest, approval.id)).status == "pending"

    async with session_factory() as db:
        binding = (await db.execute(select(TelegramApprovalBinding))).scalar_one()
        binding.revoked_at = datetime.now(UTC)
        await db.commit()
    revoked, revoked_context = approval_update(approval.id)
    await bot.approval_callback(revoked, revoked_context)
    async with session_factory() as db:
        assert (await db.get(ApprovalRequest, approval.id)).status == "pending"
        binding = (await db.execute(select(TelegramApprovalBinding))).scalar_one()
        binding.revoked_at = None
        user = await db.get(User, identity.id)
        user.role = "user"
        await db.commit()
    from app.services.telegram_pairing import resolve_telegram_auth_context

    async with session_factory() as db:
        assert await resolve_telegram_auth_context(
            db, "123456789", "123456789"
        ) is None
    demoted, demoted_context = approval_update(approval.id)
    await bot.approval_callback(demoted, demoted_context)
    async with session_factory() as db:
        assert (await db.get(ApprovalRequest, approval.id)).status == "pending"
        user = await db.get(User, identity.id)
        user.role = "admin"
        user.is_active = False
        await db.commit()
    inactive, inactive_context = approval_update(approval.id)
    await bot.approval_callback(inactive, inactive_context)
    async with session_factory() as db:
        assert (await db.get(ApprovalRequest, approval.id)).status == "pending"
    runtime[1].assert_not_awaited()


@pytest.mark.asyncio
async def test_pairing_conflict_does_not_consume_tenant_bound_challenge(
    session_factory, identity, runtime
):
    foreign_org = Organization(
        name="Foreign Telegram Tenant", slug=f"foreign-{uuid4()}", status="active"
    )
    foreign_user = User(
        id=uuid4(),
        email=f"foreign-telegram-{uuid4()}@example.invalid",
        hashed_password="fixture-only",
        role="admin",
        is_active=True,
        organization_id=foreign_org.id,
    )
    async with session_factory() as db:
        db.add(foreign_org)
        await db.flush()
        foreign_user.organization_id = foreign_org.id
        db.add(foreign_user)
        await db.commit()
    async with session_factory() as db:
        db.add(TelegramApprovalBinding(
            organization_id=foreign_org.id,
            user_id=foreign_user.id,
            telegram_user_id="123456789",
            telegram_chat_id="123456789",
        ))
        await db.commit()

    code = await create_code(session_factory, identity)
    conflicting = await pair_code(code)
    conflicting.effective_message.reply_text.assert_awaited_once()
    async with session_factory() as db:
        challenge = (await db.execute(select(TelegramPairingChallenge))).scalar_one()
        assert challenge.consumed_at is None
        assert challenge.organization_id == identity.organization_id
        bindings = list((await db.execute(select(TelegramApprovalBinding))).scalars())
        assert len(bindings) == 1
        assert bindings[0].user_id == foreign_user.id
        assert bindings[0].organization_id == foreign_org.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity_state",
    [
        "group",
        "unpaired",
        "revoked",
        "inactive",
        "missing_workflow_run",
        "missing_leads_read",
    ],
)
async def test_outreach_rejects_untrusted_or_underprivileged_telegram_callers(
    identity_state,
    runtime,
    session_factory,
    identity,
    monkeypatch,
):
    from app.agents.outreach_agent import outreach_agent

    telegram_id = "777123456"
    revoked_at = datetime.now(UTC) if identity_state == "revoked" else None
    if identity_state in {
        "revoked",
        "inactive",
        "missing_workflow_run",
        "missing_leads_read",
    }:
        async with session_factory() as db:
            user = await db.get(User, identity.id)
            if identity_state == "inactive":
                user.is_active = False
            elif identity_state == "missing_workflow_run":
                user.role = "viewer"
            elif identity_state == "missing_leads_read":
                user.role = "telegram_outreach_without_leads_read"
            db.add(
                TelegramApprovalBinding(
                    organization_id=identity.organization_id,
                    user_id=identity.id,
                    telegram_user_id=telegram_id,
                    telegram_chat_id=telegram_id,
                    revoked_at=revoked_at,
                )
            )
            await db.commit()
    if identity_state == "missing_leads_read":
        from app.auth.permissions import permissions_for_role

        def permissions_for_test_role(role):
            if role == "telegram_outreach_without_leads_read":
                return ["workflow:run"]
            return permissions_for_role(role)

        monkeypatch.setattr(
            "app.services.telegram_pairing.permissions_for_role",
            permissions_for_test_role,
        )

    run = AsyncMock(return_value={"status": "must-not-run"})
    provider_send = AsyncMock(return_value="unexpected-provider-id")
    monkeypatch.setattr(outreach_agent, "run", run)
    monkeypatch.setattr(
        "app.core.google_workspace.google_workspace.send_message", provider_send
    )

    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=int(telegram_id)),
        effective_chat=SimpleNamespace(
            id=-100123456 if identity_state == "group" else int(telegram_id),
            type="group" if identity_state == "group" else "private",
        ),
        effective_message=message,
        message=message,
    )
    forged = AuthContext(
        actor_id=str(uuid4()),
        organization_id=uuid4(),
        permissions=["workflow:run"],
        environment="production",
        auth_method="bearer_jwt",
        is_mock_auth=False,
        is_authenticated=True,
    )
    context = SimpleNamespace(args=[], bot_data={"approval_auth_context": forged})
    await bot.outreach_command(update, context)

    run.assert_not_awaited()
    provider_send.assert_not_awaited()
    if identity_state == "group":
        message.reply_text.assert_not_awaited()
    else:
        message.reply_text.assert_awaited_once()
        assert "unavailable" in message.reply_text.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_outreach_passes_only_persisted_pairing_auth_to_agent(
    runtime, session_factory, identity, monkeypatch
):
    from app.agents.outreach_agent import outreach_agent

    telegram_id = "777123457"
    async with session_factory() as db:
        user = await db.get(User, identity.id)
        user.role = "user"
        db.add(
            TelegramApprovalBinding(
                organization_id=identity.organization_id,
                user_id=identity.id,
                telegram_user_id=telegram_id,
                telegram_chat_id=telegram_id,
            )
        )
        await db.commit()

    result = {"status": "queued", "queued": 1}
    run = AsyncMock(return_value=result)
    provider_send = AsyncMock(return_value="unexpected-provider-id")
    monkeypatch.setattr(outreach_agent, "run", run)
    monkeypatch.setattr(
        "app.core.google_workspace.google_workspace.send_message", provider_send
    )
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=int(telegram_id)),
        effective_chat=SimpleNamespace(id=int(telegram_id), type="private"),
        effective_message=message,
        message=message,
    )
    forged = AuthContext(
        actor_id=str(uuid4()),
        organization_id=uuid4(),
        permissions=["workflow:run"],
        environment="production",
        auth_method="bearer_jwt",
        is_mock_auth=False,
        is_authenticated=True,
    )
    context = SimpleNamespace(args=[], bot_data={"approval_auth_context": forged})

    await bot.outreach_command(update, context)

    run.assert_awaited_once()
    passed_auth = run.await_args.kwargs["auth"]
    assert passed_auth.actor_id == str(identity.id)
    assert passed_auth.organization_id == identity.organization_id
    assert passed_auth.auth_method == "telegram_binding"
    assert passed_auth.has_permission("workflow:run")
    assert passed_auth.has_permission("leads:read")
    assert not passed_auth.has_permission("approvals:resolve")
    provider_send.assert_not_awaited()
    update.effective_message.reply_text.assert_awaited_once_with(str(result))


@pytest.mark.asyncio
async def test_approval_notifications_route_only_to_active_owner_private_chats(
    runtime, session_factory, default_org, identity, monkeypatch, caplog
):
    from app.config import settings
    from app.core.control_plane import _notify_approval_request
    from app.models.organization import Organization

    foreign_org = Organization(
        id=uuid4(),
        name="Foreign Tenant",
        slug=f"foreign-{uuid4()}",
        status="active",
    )
    foreign_user = User(
        id=uuid4(),
        email=f"foreign-{uuid4()}@example.invalid",
        hashed_password="fixture-only",
        role="admin",
        is_active=True,
        organization_id=foreign_org.id,
    )
    async with session_factory() as db:
        db.add(foreign_org)
        await db.flush()
        db.add(foreign_user)
        await db.flush()
        db.add_all(
            [
                TelegramApprovalBinding(
                    organization_id=identity.organization_id,
                    user_id=identity.id,
                    telegram_user_id="777123458",
                    telegram_chat_id="777123458",
                ),
                TelegramApprovalBinding(
                    organization_id=identity.organization_id,
                    user_id=identity.id,
                    telegram_user_id="777123459",
                    telegram_chat_id="777123459",
                    revoked_at=datetime.now(UTC),
                ),
                TelegramApprovalBinding(
                    organization_id=foreign_org.id,
                    user_id=foreign_user.id,
                    telegram_user_id="777123460",
                    telegram_chat_id="777123460",
                ),
            ]
        )
        await db.commit()

    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "777123999")
    notification = SimpleNamespace(
        id=uuid4(),
        organization_id=identity.organization_id,
        title="Email [owner]*_{a}@example.invalid",
        action_type="network_message_send",
        requested_by="outreach_agent",
        expires_at=None,
        batch_key=None,
    )
    await _notify_approval_request(notification)

    notify = runtime[1]
    notify.assert_awaited_once()
    kwargs = notify.await_args.kwargs
    assert kwargs["chat_id"] == "777123458"
    assert kwargs["parse_mode"] is None
    assert "Email [owner]*_{a}@example.invalid" in notify.await_args.args[0]
    assert "777123999" not in repr(notify.await_args)

    notify.reset_mock()
    notify.return_value = False
    with caplog.at_level("WARNING", logger="app.core.control_plane"):
        await _notify_approval_request(notification)
    notify.assert_awaited_once()
    assert f"approval_id={notification.id}" in caplog.text
    assert "action_type=network_message_send" in caplog.text
    assert "Email [owner]*_{a}@example.invalid" not in caplog.text

    notify.reset_mock()
    notify.side_effect = RuntimeError("fixture failure with private detail")
    caplog.clear()
    with caplog.at_level("WARNING", logger="app.core.control_plane"):
        await _notify_approval_request(notification)
    notify.assert_awaited_once()
    assert f"approval_id={notification.id}" in caplog.text
    assert "action_type=network_message_send" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "fixture failure with private detail" not in caplog.text
    assert "Email [owner]*_{a}@example.invalid" not in caplog.text
    notify.side_effect = None

    notify.reset_mock()
    no_binding_approval = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        title="Must stay in REST queue",
        action_type="network_message_send",
        requested_by="outreach_agent",
        expires_at=None,
        batch_key=None,
    )
    await _notify_approval_request(no_binding_approval)
    notify.assert_not_awaited()


class _FakeBot:
    def __init__(self, send_message):
        self.send_message = send_message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _patch_telegram_bot(monkeypatch, send_message):
    monkeypatch.setattr(bot, "Bot", lambda token: _FakeBot(send_message))


@pytest.mark.asyncio
async def test_explicit_telegram_target_never_falls_back_to_global_chat(monkeypatch):
    from app.config import settings

    target_send = AsyncMock()
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "123456:offline-test-token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")
    _patch_telegram_bot(monkeypatch, target_send)

    sent = await bot.send_message("private approval", parse_mode=None, chat_id="777123458")
    rejected = await bot.send_message("private approval", chat_id="invalid")

    assert sent is True
    assert rejected is False
    target_send.assert_awaited_once()
    assert target_send.await_args.kwargs["chat_id"] == "777123458"
    assert target_send.await_args.kwargs["parse_mode"] is None


@pytest.mark.asyncio
async def test_telegram_send_failure_logs_no_provider_exception_details(
    monkeypatch, caplog
):
    from app.config import settings

    private_error = "private recipient@example.invalid provider-response-secret"
    target_send = AsyncMock(side_effect=RuntimeError(private_error))
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "123456:offline-test-token")
    _patch_telegram_bot(monkeypatch, target_send)

    with caplog.at_level("ERROR", logger="app.telegram_bot.bot"):
        delivered = await bot.send_message("fixture message", chat_id="777123458")

    assert delivered is False
    target_send.assert_awaited_once()
    assert "RuntimeError" in caplog.text
    assert private_error not in caplog.text
    assert "recipient@example.invalid" not in caplog.text
    assert "provider-response-secret" not in caplog.text


@pytest.mark.asyncio
async def test_legacy_approval_send_failure_logs_no_provider_details(
    monkeypatch, caplog
):
    from app.config import settings

    private_error = "approval recipient@example.invalid provider-response-secret"
    target_send = AsyncMock(side_effect=RuntimeError(private_error))
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "777123458")
    monkeypatch.setattr(
        bot,
        "_app",
        SimpleNamespace(bot=SimpleNamespace(send_message=target_send)),
    )

    with caplog.at_level("ERROR", logger="app.telegram_bot.bot"):
        delivered = await bot.send_approval_request("approval-123", "fixture", "send_email")

    assert delivered is False
    target_send.assert_awaited_once()
    assert "RuntimeError" in caplog.text
    assert private_error not in caplog.text
    assert "recipient@example.invalid" not in caplog.text
    assert "provider-response-secret" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_text", "message_fragment", "retry_delay"),
    [
        (
            "Conflict: private recipient@example.invalid provider-secret",
            "polling conflict detected",
            60,
        ),
        (
            "private recipient@example.invalid provider-secret",
            "polling crashed",
            10,
        ),
    ],
)
async def test_polling_error_logs_no_provider_details(
    monkeypatch, caplog, error_text, message_fragment, retry_delay
):
    attempts = 0

    async def start_polling():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError(error_text)
        raise asyncio.CancelledError

    sleep = AsyncMock()
    stop = AsyncMock()
    monkeypatch.setattr(bot, "start_polling", start_polling)
    monkeypatch.setattr(bot, "stop_polling", stop)
    monkeypatch.setattr(bot.asyncio, "sleep", sleep)

    with caplog.at_level("WARNING", logger="app.telegram_bot.bot"):
        with pytest.raises(asyncio.CancelledError):
            await bot.run_polling_forever()

    assert message_fragment in caplog.text.lower()
    assert "RuntimeError" in caplog.text
    assert error_text not in caplog.text
    assert "recipient@example.invalid" not in caplog.text
    assert "provider-secret" not in caplog.text
    sleep.assert_awaited_once_with(retry_delay)
    assert stop.await_count == 2


@pytest.mark.asyncio
async def test_default_telegram_message_keeps_global_operational_route(monkeypatch):
    from app.config import settings

    target_send = AsyncMock()
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "123456:offline-test-token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "777123999")
    _patch_telegram_bot(monkeypatch, target_send)

    sent = await bot.send_message("operational notice")

    assert sent is True
    target_send.assert_awaited_once()
    assert target_send.await_args.kwargs["chat_id"] == "777123999"


async def _persist_telegram_binding(session_factory, identity, *, role=None, revoked=False):
    async with session_factory() as db:
        user = await db.get(User, identity.id)
        if role is not None:
            user.role = role
        db.add(
            TelegramApprovalBinding(
                organization_id=identity.organization_id,
                user_id=identity.id,
                telegram_user_id="123456789",
                telegram_chat_id="123456789",
                revoked_at=datetime.now(UTC) if revoked else None,
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_telegram_read_commands_return_only_current_tenant_records(
    session_factory, identity, runtime
):
    from app.models.assistant_task import AssistantTask
    from app.models.contact import Contact
    from app.models.email_thread import EmailThread
    from app.models.job_posting import JobPosting

    foreign_org = Organization(
        name="Foreign Read Tenant", slug=f"foreign-read-{uuid4()}", status="active"
    )
    await _persist_telegram_binding(session_factory, identity, role="viewer")
    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add(foreign_org)
        await db.flush()
        db.add_all(
            [
                JobPosting(
                    organization_id=identity.organization_id,
                    title="OWN_JOB_MARKER",
                    company="Own Co",
                    source_platform="fixture",
                    job_type="job",
                    match_score=9,
                    status="discovered",
                ),
                JobPosting(
                    organization_id=foreign_org.id,
                    title="FOREIGN_JOB_MARKER",
                    company="Foreign Co",
                    source_platform="fixture",
                    job_type="job",
                    match_score=10,
                    status="discovered",
                ),
                Contact(
                    organization_id=identity.organization_id,
                    name="OWN_CONTACT_MARKER",
                    role="Owner",
                    company="Own Co",
                    value_score=9,
                    is_deleted=False,
                ),
                Contact(
                    organization_id=foreign_org.id,
                    name="FOREIGN_CONTACT_MARKER",
                    role="Foreign",
                    company="Foreign Co",
                    value_score=10,
                    is_deleted=False,
                ),
                AssistantTask(
                    organization_id=identity.organization_id,
                    title="OWN_TASK_MARKER",
                    priority=9,
                    status="pending",
                    due_date=now,
                ),
                AssistantTask(
                    organization_id=foreign_org.id,
                    title="FOREIGN_TASK_MARKER",
                    priority=10,
                    status="pending",
                    due_date=now,
                ),
                EmailThread(
                    organization_id=identity.organization_id,
                    thread_id=f"own-{uuid4()}",
                    subject="Own email",
                    unread_count=2,
                ),
                EmailThread(
                    organization_id=foreign_org.id,
                    thread_id=f"foreign-{uuid4()}",
                    subject="Foreign email",
                    unread_count=7,
                ),
            ]
        )
        await db.commit()

    responses = []
    for command in (
        bot.status_command,
        bot.jobs_command,
        bot.contacts_command,
        bot.tasks_command,
    ):
        update, context, message = read_command_update()
        await command(update, context)
        message.reply_text.assert_awaited_once()
        responses.append(message.reply_text.await_args.args[0])

    status, jobs, contacts, tasks = responses
    assert "Jobs: 1" in status
    assert "Contacts: 1" in status
    assert "Pending Tasks: 1" in status
    assert "Unread Emails: 1" in status
    assert "OWN_JOB_MARKER" in jobs and "FOREIGN_JOB_MARKER" not in jobs
    assert "OWN_CONTACT_MARKER" in contacts and "FOREIGN_CONTACT_MARKER" not in contacts
    assert "OWN_TASK_MARKER" in tasks and "FOREIGN_TASK_MARKER" not in tasks
    for response in responses:
        assert "FOREIGN_" not in response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [bot.status_command, bot.jobs_command, bot.contacts_command, bot.tasks_command],
)
async def test_read_commands_require_persisted_private_identity(
    command, session_factory, identity, runtime
):
    update, context, message = read_command_update()
    await command(update, context)
    message.reply_text.assert_awaited_once()
    assert "unavailable" in message.reply_text.await_args.args[0].lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity_state",
    [
        "group",
        "wrong_chat",
        "unpaired",
        "revoked",
        "inactive_user",
        "inactive_org",
        "permission_changed",
    ],
)
async def test_telegram_read_identity_and_current_permission_fail_closed(
    identity_state, session_factory, identity, runtime
):
    role = "admin" if identity_state == "permission_changed" else "viewer"
    if identity_state != "unpaired":
        await _persist_telegram_binding(
            session_factory,
            identity,
            role=role,
            revoked=identity_state == "revoked",
        )
    async with session_factory() as db:
        if identity_state == "permission_changed":
            user = await db.get(User, identity.id)
            user.role = "unknown-role"
            await db.commit()
        elif identity_state == "inactive_user":
            user = await db.get(User, identity.id)
            user.is_active = False
            await db.commit()
        elif identity_state == "inactive_org":
            organization = await db.get(Organization, identity.organization_id)
            organization.status = "suspended"
            await db.commit()

    telegram_id = "123456789"
    chat_id = telegram_id
    if identity_state == "group":
        chat_id = "-1007654321"
    elif identity_state == "wrong_chat":
        chat_id = "7654321"
    update, context, message = read_command_update(
        telegram_id=int(telegram_id),
        chat_id=int(chat_id),
        chat_type="group" if identity_state == "group" else "private",
    )
    await bot.tasks_command(update, context)
    if identity_state == "group":
        message.reply_text.assert_not_awaited()
    else:
        message.reply_text.assert_awaited_once()
        assert "unavailable" in message.reply_text.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_costs_and_briefing_are_disabled_without_tenant_attribution(
    session_factory, identity, runtime, monkeypatch
):
    from app.agents.personal_assistant import personal_assistant_agent
    from app.models.openclaw_usage import OpenClawUsage

    await _persist_telegram_binding(session_factory, identity, role="admin")
    assert not hasattr(OpenClawUsage, "organization_id")
    briefing = AsyncMock(return_value="UNSCOPED_BRIEFING")
    monkeypatch.setattr(personal_assistant_agent, "generate_daily_briefing", briefing)

    for command in (bot.costs_command, bot.briefing_command):
        update, context, message = read_command_update()
        await command(update, context)
        message.reply_text.assert_awaited_once()
        assert "unavailable" in message.reply_text.await_args.args[0].lower()
        assert "UNSCOPED_BRIEFING" not in message.reply_text.await_args.args[0]
    briefing.assert_not_awaited()


@pytest.mark.asyncio
async def test_briefing_denies_role_without_workflow_run(
    session_factory, identity, runtime
):
    await _persist_telegram_binding(session_factory, identity, role="viewer")
    update, context, message = read_command_update()

    await bot.briefing_command(update, context)

    message.reply_text.assert_awaited_once()
    assert "permission" in message.reply_text.await_args.args[0].lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [bot.status_command, bot.jobs_command, bot.contacts_command, bot.tasks_command],
)
async def test_telegram_read_failure_logs_only_exception_type(
    command, monkeypatch, caplog
):
    auth = AuthContext(
        actor_id=str(uuid4()),
        organization_id=uuid4(),
        permissions=["system:read", "workflow:read", "leads:read"],
        environment="production",
        auth_method="telegram_binding",
        is_mock_auth=False,
        is_authenticated=True,
    )

    class FailingSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def execute(self, *args, **kwargs):
            raise RuntimeError("private@example.invalid provider-secret")

    monkeypatch.setattr(
        bot, "_telegram_read_auth_context", AsyncMock(return_value=auth)
    )
    monkeypatch.setattr(bot, "AsyncSessionLocal", FailingSession)
    update, context, message = read_command_update()

    with caplog.at_level("ERROR", logger="app.telegram_bot.bot"):
        await command(update, context)

    assert "RuntimeError" in caplog.text
    assert "private@example.invalid" not in caplog.text
    assert "provider-secret" not in caplog.text
    message.reply_text.assert_awaited_once()
