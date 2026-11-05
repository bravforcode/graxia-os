"""Invitation mutations share the caller's transaction with account creation."""
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update

from app.models.invitation import Invitation
from app.models.organization import Organization
from app.auth.tenant_identity import require_active_organization
from app.models.user import User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_invitation_owner(user: User) -> None:
    if not user.is_active or user.role not in {"owner", "admin"} or not user.organization_id:
        raise HTTPException(403, "Invitation administration requires an organization owner")


async def issue_invitation(db, owner: User, email: str, role: str) -> tuple[Invitation, str]:
    require_invitation_owner(owner)
    await require_active_organization(db, owner.organization_id)
    if role not in {"operator", "viewer"}:
        raise HTTPException(400, "Invalid invitation role")
    token = secrets.token_urlsafe(32)
    invitation = Invitation(
        organization_id=owner.organization_id, issued_by=owner.id,
        email=normalize_email(email), role=role, token_digest=token_digest(token),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(invitation)
    await db.flush()
    return invitation, token


async def revoke_invitation(db, owner: User, invitation_id: UUID) -> None:
    require_invitation_owner(owner)
    await require_active_organization(db, owner.organization_id)
    result = await db.execute(update(Invitation).where(
        Invitation.id == invitation_id, Invitation.organization_id == owner.organization_id,
        Invitation.consumed_at.is_(None), Invitation.revoked_at.is_(None),
    ).values(revoked_at=datetime.now(UTC)))
    if result.rowcount != 1:
        raise HTTPException(404, "Invitation not available")


async def consume_invitation(db, token: str | None, email: str) -> Invitation:
    if not token:
        raise HTTPException(403, "Valid invitation required")
    digest = token_digest(token)
    now = datetime.now(UTC)
    # Conditional UPDATE provides single-winner consumption on SQLite and PostgreSQL.
    result = await db.execute(update(Invitation).where(
        Invitation.token_digest == digest, Invitation.email == normalize_email(email),
        Invitation.expires_at > now, Invitation.consumed_at.is_(None),
        Invitation.revoked_at.is_(None),
        select(Organization.id).where(
            Organization.id == Invitation.organization_id,
            Organization.status.in_(("active", "trialing")),
        ).exists(),
    ).values(consumed_at=now).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(403, "Valid invitation required")
    invitation = (await db.execute(select(Invitation).where(Invitation.token_digest == digest))).scalar_one()
    if invitation.role not in {"operator", "viewer"} or not invitation.organization_id:
        raise HTTPException(403, "Valid invitation required")
    return invitation
