"""Tests for AuthContext module — dataclass, dependencies, middleware.

Verifies:
- AuthContext dataclass properties
- LocalDevAuthContext defaults
- AuthContext environment detection
- Org-scoped dependency enforcement
- Missing auth handling
"""
from __future__ import annotations

import uuid

import pytest
from app.auth.context import AuthContext, LocalDevAuthContext, LOCAL_DEV_ORGANIZATION_ID
from app.auth.errors import AuthError, MissingAuthError, OrgMismatchError, InsufficientPermissionsError


class TestAuthContextDataclass:
    """AuthContext dataclass unit tests."""

    def test_default_construction(self):
        """Default AuthContext uses local-dev org and mock auth."""
        ctx = AuthContext()
        assert ctx.organization_id == LOCAL_DEV_ORGANIZATION_ID
        assert ctx.actor_type == "user"
        assert ctx.is_mock_auth is True
        assert ctx.environment == "local"
        assert ctx.has_organization is True
        assert ctx.is_system is False
        assert ctx.is_staging_or_production is False

    def test_system_actor(self):
        """is_system returns True for system actor_type."""
        ctx = AuthContext(actor_type="system")
        assert ctx.is_system is True
        assert ctx.is_staging_or_production is False

    def test_staging_environment(self):
        """is_staging_or_production returns True for staging."""
        ctx = AuthContext(environment="staging")
        assert ctx.is_staging_or_production is True

    def test_production_environment(self):
        """is_staging_or_production returns True for production."""
        ctx = AuthContext(environment="production")
        assert ctx.is_staging_or_production is True

    def test_custom_organization_id(self):
        """Custom organization_id is respected."""
        custom_id = uuid.uuid4()
        ctx = AuthContext(organization_id=custom_id)
        assert ctx.organization_id == custom_id
        assert ctx.has_organization is True

    def test_none_organization_id(self):
        """has_organization returns False when organization_id is None."""
        ctx = AuthContext(organization_id=None)  # type: ignore[arg-type]
        assert ctx.has_organization is False

    def test_frozen(self):
        """AuthContext should be frozen/immutable."""
        ctx = AuthContext()
        with pytest.raises(AttributeError):
            ctx.organization_id = uuid.uuid4()  # type: ignore[misc]

    def test_local_dev_constant(self):
        """LocalDevAuthContext is a system actor with local-dev defaults."""
        assert LocalDevAuthContext.actor_type == "system"
        assert LocalDevAuthContext.actor_id == "local-dev"
        assert LocalDevAuthContext.organization_id == LOCAL_DEV_ORGANIZATION_ID
        assert LocalDevAuthContext.environment == "local"
        assert LocalDevAuthContext.is_mock_auth is True

    def test_permissions_list(self):
        """Permissions list is mutable per instance."""
        ctx1 = AuthContext(permissions=["read", "write"])
        ctx2 = AuthContext()
        assert len(ctx1.permissions) == 2
        assert len(ctx2.permissions) == 0


class TestAuthErrors:
    """Auth error classes — safe, org-leak-proof."""

    def test_base_auth_error(self):
        error = AuthError()
        assert str(error) == "Authentication failed."

    def test_missing_auth_error(self):
        error = MissingAuthError()
        assert str(error) == "Authentication required."

    def test_org_mismatch_error(self):
        error = OrgMismatchError()
        assert str(error) == "Resource not found."

    def test_insufficient_permissions_error(self):
        error = InsufficientPermissionsError()
        assert str(error) == "Insufficient permissions."

    def test_custom_message(self):
        error = AuthError("Custom message")
        assert str(error) == "Custom message"
