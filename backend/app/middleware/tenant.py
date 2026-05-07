"""
Tenant isolation.
Auto-creates personal org for new users.
Blocks canceled/suspended accounts.
"""

import logging

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.organization import Organization
from app.models.user import User
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("graxia.tenant")


async def get_org(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Organization:
    """
    FastAPI dependency: resolves current org, auto-creates if missing.
    Attach with: org: Organization = Depends(get_org)
    """

    if not user.organization_id:
        # First login — create personal workspace
        slug = f"u-{user.id}"
        org = Organization(
            name=f"{(user.full_name or user.email).split('@')[0]}'s Workspace",
            slug=slug,
            plan="free",
            status="active",
        )
        org.apply_plan_limits()
        db.add(org)
        await db.flush()
        await db.refresh(org)

        user.organization_id = org.id
        await db.commit()
        log.info(f"Auto-created org {org.id} for user {user.id}")
    else:
        org = await db.get(Organization, user.organization_id)

    if not org:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Organization not found. Contact support.",
        )

    if org.status == "canceled":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription canceled. Renew at /billing to continue.",
        )
    if org.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended. Contact support@graxia.io",
        )

    request.state.organization = org
    return org
