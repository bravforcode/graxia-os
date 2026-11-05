"""Telegram pairing verification and persisted owner resolution."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.auth.permissions import permissions_for_role
from app.models.organization import Organization
from app.models.telegram_pairing import TelegramApprovalBinding, TelegramPairingChallenge
from app.models.user import User


def _hash_pairing_code(code: str) -> str | None:
    if not isinstance(code, str) or not code or len(code) > 128:
        return None
    try:
        return hashlib.sha256(code.encode("ascii")).hexdigest()
    except UnicodeEncodeError:
        return None


def _valid_telegram_id(value: str) -> bool:
    return bool(value) and value.isascii() and value.isdecimal() and int(value) > 0


async def consume_pairing_code(
    db: AsyncSession,
    code: str,
    telegram_user_id: str,
    telegram_chat_id: str,
) -> bool:
    """Consume one live code and atomically establish its active private binding."""
    token_hash = _hash_pairing_code(code)
    if (
        token_hash is None
        or not _valid_telegram_id(telegram_user_id)
        or telegram_chat_id != telegram_user_id
    ):
        return False

    now = datetime.now(UTC)
    candidate = (
        await db.execute(
            select(TelegramPairingChallenge)
            .where(
                TelegramPairingChallenge.token_hash == token_hash,
                TelegramPairingChallenge.consumed_at.is_(None),
                TelegramPairingChallenge.revoked_at.is_(None),
                TelegramPairingChallenge.expires_at > now,
            )
        )
    ).scalar_one_or_none()
    if candidate is None:
        return False

    user = (
        await db.execute(
            select(User).where(User.id == candidate.user_id).with_for_update()
        )
    ).scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or user.organization_id != candidate.organization_id
        or "approvals:resolve" not in permissions_for_role(user.role)
    ):
        return False

    organization = await db.get(Organization, candidate.organization_id)
    if organization is None or not organization.is_active:
        return False

    active_binding = (
        await db.execute(
            select(TelegramApprovalBinding)
            .where(
                TelegramApprovalBinding.revoked_at.is_(None),
                or_(
                    TelegramApprovalBinding.telegram_user_id == telegram_user_id,
                    TelegramApprovalBinding.user_id == user.id,
                ),
            )
            .with_for_update()
        )
    ).scalars().all()
    if any(
        binding.telegram_user_id != telegram_user_id
        or binding.user_id != user.id
        or binding.organization_id != user.organization_id
        for binding in active_binding
    ):
        return False

    # Match revoke_pairing's lock order: User → active Binding → Challenge.
    # The first challenge read only identifies the owner; re-check every
    # redeemable predicate after the owner and binding locks are held.
    challenge = (
        await db.execute(
            select(TelegramPairingChallenge)
            .where(
                TelegramPairingChallenge.id == candidate.id,
                TelegramPairingChallenge.token_hash == token_hash,
                TelegramPairingChallenge.user_id == user.id,
                TelegramPairingChallenge.organization_id == user.organization_id,
                TelegramPairingChallenge.consumed_at.is_(None),
                TelegramPairingChallenge.revoked_at.is_(None),
                TelegramPairingChallenge.expires_at > now,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if challenge is None:
        return False

    consumed = await db.execute(
        update(TelegramPairingChallenge)
        .where(
            TelegramPairingChallenge.id == challenge.id,
            TelegramPairingChallenge.token_hash == token_hash,
            TelegramPairingChallenge.consumed_at.is_(None),
            TelegramPairingChallenge.revoked_at.is_(None),
            TelegramPairingChallenge.expires_at > now,
        )
        .values(consumed_at=now)
        .execution_options(synchronize_session=False)
    )
    if consumed.rowcount != 1:
        return False

    if active_binding:
        active_binding[0].telegram_chat_id = telegram_chat_id
    else:
        db.add(
            TelegramApprovalBinding(
                organization_id=user.organization_id,
                user_id=user.id,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
            )
        )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return False
    return True


async def resolve_telegram_auth_context(
    db: AsyncSession,
    telegram_user_id: str,
    telegram_chat_id: str,
) -> AuthContext | None:
    """Build approval authority; Telegram approvals require the resolve grant."""
    return await _resolve_bound_telegram_auth_context(
        db,
        telegram_user_id,
        telegram_chat_id,
        required_permission="approvals:resolve",
    )


async def resolve_telegram_read_auth_context(
    db: AsyncSession,
    telegram_user_id: str,
    telegram_chat_id: str,
    *,
    required_permission: str,
) -> AuthContext | None:
    """Resolve read-command authority from binding and current role."""
    return await _resolve_bound_telegram_auth_context(
        db,
        telegram_user_id,
        telegram_chat_id,
        required_permission=required_permission,
    )


async def _resolve_bound_telegram_auth_context(
    db: AsyncSession,
    telegram_user_id: str,
    telegram_chat_id: str,
    *,
    required_permission: str,
) -> AuthContext | None:
    """Resolve identity from an active private binding and current DB state."""
    if (
        not _valid_telegram_id(telegram_user_id)
        or telegram_chat_id != telegram_user_id
    ):
        return None

    binding = (
        await db.execute(
            select(TelegramApprovalBinding).where(
                TelegramApprovalBinding.telegram_user_id == telegram_user_id,
                TelegramApprovalBinding.telegram_chat_id == telegram_chat_id,
                TelegramApprovalBinding.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if binding is None:
        return None

    user = await db.get(User, binding.user_id)
    if (
        user is None
        or not user.is_active
        or user.organization_id != binding.organization_id
    ):
        return None

    permissions = permissions_for_role(user.role)
    if required_permission not in permissions:
        return None

    organization = await db.get(Organization, binding.organization_id)
    if organization is None or not organization.is_active:
        return None

    return AuthContext(
        actor_type="admin" if user.role == "admin" else "user",
        actor_id=str(user.id),
        organization_id=user.organization_id,
        permissions=permissions,
        environment="production",
        auth_method="telegram_binding",
        is_mock_auth=False,
        is_authenticated=True,
        is_internal=False,
        is_customer=False,
    )
