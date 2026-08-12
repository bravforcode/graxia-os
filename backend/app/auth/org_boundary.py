"""Organization boundary helpers for Phase 16."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.auth.context import AuthContext


def require_organization_id(auth: AuthContext) -> UUID:
    if not auth.organization_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Organization context required.",
        )
    return auth.organization_id


def assert_same_org(auth: AuthContext, resource_org_id: UUID | str | None) -> None:
    current_org = require_organization_id(auth)
    if resource_org_id is None or str(current_org) != str(resource_org_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found.",
        )
