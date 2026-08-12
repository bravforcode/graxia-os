"""Auth errors — safe, org-leak-proof error classes."""
from __future__ import annotations


class AuthError(Exception):
    """Base auth error — message is safe for API responses."""

    def __init__(self, message: str = "Authentication failed.") -> None:
        self.message = message
        super().__init__(self.message)


class MissingAuthError(AuthError):
    """No auth context provided — safe 401 equivalent."""

    def __init__(self, message: str = "Authentication required.") -> None:
        super().__init__(message)


class OrgMismatchError(AuthError):
    """Organization ID mismatch — never reveal whether the target org exists."""

    def __init__(self, message: str = "Resource not found.") -> None:
        super().__init__(message)


class InsufficientPermissionsError(AuthError):
    """Actor lacks required permissions."""

    def __init__(self, message: str = "Insufficient permissions.") -> None:
        super().__init__(message)
