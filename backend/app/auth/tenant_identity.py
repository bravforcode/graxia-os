"""Persisted organization status gate for enrolled identities."""
from fastapi import HTTPException

from app.models.organization import Organization


async def require_active_organization(db, organization_id) -> None:
    # Keep existing unscoped-account behavior; tenant routes enforce their scope.
    if organization_id is None:
        return
    organization = await db.get(Organization, organization_id, populate_existing=True)
    if organization is None or not organization.is_active:
        raise HTTPException(403, "Organization is unavailable")
