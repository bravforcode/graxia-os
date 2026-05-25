"""AuthContext — organization-scoped authentication for staging/production."""
from app.auth.context import AuthContext, LocalDevAuthContext
from app.auth.dependencies import (
    get_auth_context,
    require_organization,
    require_staging_auth,
    optional_auth_context,
)
from app.auth.errors import AuthError, OrgMismatchError, MissingAuthError
from app.auth.middleware import AuthContextMiddleware

__all__ = [
    "AuthContext",
    "LocalDevAuthContext",
    "get_auth_context",
    "require_organization",
    "require_staging_auth",
    "optional_auth_context",
    "AuthError",
    "OrgMismatchError",
    "MissingAuthError",
    "AuthContextMiddleware",
]
