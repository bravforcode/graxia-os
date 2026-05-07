"""
API Dependencies
Common dependencies for API endpoints
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.middleware.auth import get_current_user
from app.middleware.tenant import get_org
from app.models.organization import Organization
from app.models.user import User


async def get_tenant_db(current_user: User = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        if current_user.organization_id:
            await session.execute(text(f"SET LOCAL myapp.current_tenant_id = '{current_user.organization_id}'"))
        try:
            yield session
        finally:
            if current_user.organization_id:
                await session.execute(text("RESET myapp.current_tenant_id"))


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

__all__ = ["get_tenant_db", "get_org", "get_current_user", "require_admin"]
