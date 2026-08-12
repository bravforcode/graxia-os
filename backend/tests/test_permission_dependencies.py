"""Phase 16 permission model tests."""
from __future__ import annotations

from app.auth.context import AuthContext
from app.auth.permissions import auth_context_has_permission, permissions_for_role


def test_admin_role_includes_security_sensitive_permissions():
    perms = permissions_for_role("admin")
    assert "system:read" in perms
    assert "approvals:resolve" in perms
    assert "workflow:run" in perms
    assert "analytics:read" in perms


def test_viewer_role_is_read_only():
    perms = permissions_for_role("viewer")
    assert "funnel:read" in perms
    assert "workflow:read" in perms
    assert "funnel:write" not in perms
    assert "approvals:resolve" not in perms


def test_auth_context_has_permission_checks_list():
    auth = AuthContext(
        actor_type="user",
        permissions=["analytics:read", "workflow:read"],
        is_authenticated=True,
        is_mock_auth=False,
    )
    assert auth_context_has_permission(auth, "analytics:read") is True
    assert auth_context_has_permission(auth, "workflow:run") is False


def test_system_bypass_retains_local_dev_behavior():
    auth = AuthContext(
        actor_type="system",
        actor_id="local-dev",
        permissions=[],
        is_authenticated=True,
        is_mock_auth=True,
    )
    assert auth_context_has_permission(auth, "admin:write") is True
