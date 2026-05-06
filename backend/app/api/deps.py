"""
API Dependencies
Common dependencies for API endpoints
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.organization import Organization
from app.models.user import User


async def get_org(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Get current user's organization."""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no organization",
        )
    org = await db.get(Organization, current_user.organization_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return org



async def require_admin(
    current_user: "User" = Depends(get_current_user),
) -> "User":
    """FastAPI dependency — rejects non-admin callers with HTTP 403."""
    from app.middleware.auth import role_satisfies, AuthLevel, ROLE_ORDER
    user_role = getattr(current_user, "role", "user") or "user"
    if ROLE_ORDER.get(user_role, -1) < ROLE_ORDER.get("admin", 3):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user

__all__ = ["get_db", "get_org", "get_current_user", "require_admin"]
