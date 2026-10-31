"""Authenticated API for creating and revoking Telegram owner pairings."""
from datetime import UTC, datetime, timedelta
import hashlib
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.auth.dependencies import require_permission
from app.auth.permissions import permissions_for_role
from app.database import get_db
from app.models.organization import Organization
from app.models.telegram_pairing import TelegramApprovalBinding, TelegramPairingChallenge
from app.models.user import User

router = APIRouter(prefix="/telegram", tags=["telegram"])
DbSession = Depends(get_db)
PAIRING_CODE_BYTES = 32
PAIRING_TTL = timedelta(minutes=10)


class PairingChallengeResponse(BaseModel):
    pairing_code: str
    expires_at: datetime
    instruction: str


class PairingRevocationResponse(BaseModel):
    status: str


async def _authenticated_owner(db: AsyncSession, auth: AuthContext | None) -> User:
    if (
        not isinstance(auth, AuthContext)
        or not auth.is_authenticated
        or auth.is_mock_auth
        or auth.auth_method != "bearer_jwt"
        or not auth.has_permission("approvals:resolve")
    ):
        raise HTTPException(status_code=401, detail="Authenticated owner required")
    try:
        actor_id = UUID(str(auth.actor_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=401, detail="Authenticated owner required") from None

    user = (
        await db.execute(select(User).where(User.id == actor_id).with_for_update())
    ).scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or not isinstance(user.organization_id, UUID)
        or user.organization_id.int == 0
        or user.organization_id != auth.organization_id
        or "approvals:resolve" not in permissions_for_role(user.role)
    ):
        raise HTTPException(status_code=403, detail="Active approval owner required")

    organization = await db.get(Organization, user.organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(status_code=403, detail="Active approval owner required")
    return user


@router.post("/pairing-challenges", response_model=PairingChallengeResponse)
async def create_pairing_challenge(
    db: AsyncSession = DbSession,
    auth: AuthContext = Depends(require_permission("approvals:resolve")),
) -> PairingChallengeResponse:
    """Issue a high-entropy code once; only its SHA-256 digest is persisted."""
    user = await _authenticated_owner(db, auth)
    code = secrets.token_urlsafe(PAIRING_CODE_BYTES)
    now = datetime.now(UTC)
    expires_at = now + PAIRING_TTL
    db.add(
        TelegramPairingChallenge(
            organization_id=user.organization_id,
            user_id=user.id,
            token_hash=hashlib.sha256(code.encode("ascii")).hexdigest(),
            expires_at=expires_at,
        )
    )
    await db.commit()
    return PairingChallengeResponse(
        pairing_code=code,
        expires_at=expires_at,
        instruction="Send /pair <pairing_code> to the bot in a private chat within 10 minutes.",
    )


@router.delete("/pairing", response_model=PairingRevocationResponse)
async def revoke_pairing(
    db: AsyncSession = DbSession,
    auth: AuthContext = Depends(require_permission("approvals:resolve")),
) -> PairingRevocationResponse:
    """Revoke this account's active Telegram binding and unused challenges."""
    user = await _authenticated_owner(db, auth)
    now = datetime.now(UTC)
    result = await db.execute(
        update(TelegramApprovalBinding)
        .where(
            TelegramApprovalBinding.organization_id == user.organization_id,
            TelegramApprovalBinding.user_id == user.id,
            TelegramApprovalBinding.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.execute(
        update(TelegramPairingChallenge)
        .where(
            TelegramPairingChallenge.organization_id == user.organization_id,
            TelegramPairingChallenge.user_id == user.id,
            TelegramPairingChallenge.consumed_at.is_(None),
            TelegramPairingChallenge.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.commit()
    return PairingRevocationResponse(status="revoked" if result.rowcount else "not_bound")
