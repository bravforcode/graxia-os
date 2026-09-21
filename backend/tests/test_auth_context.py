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
from fastapi import HTTPException
from app.auth.context import AuthContext, LocalDevAuthContext, LOCAL_DEV_ORGANIZATION_ID
from app.auth.dependencies import get_auth_context
from app.auth.errors import AuthError, MissingAuthError, OrgMismatchError, InsufficientPermissionsError
from starlette.requests import Request


def _request_with_auth_payload(payload: dict | None) -> Request:
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    if payload is not None:
        request.state.auth_payload = payload
    return request


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


class TestAuthContextDependency:
    """Auth dependency tenant resolution."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("environment", ["staging", "production"])
    async def test_client_permissions_header_cannot_elevate_verified_role(
        self, monkeypatch, environment
    ):
        monkeypatch.setattr("app.auth.dependencies.settings.APP_ENV", environment)
        org_id = uuid.uuid4()
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"x-graxia-permissions", b"admin:write")],
            }
        )
        request.state.auth_payload = {
            "organization_id": str(org_id),
            "role": "viewer",
        }
        request.state.authenticated_role = "viewer"

        auth = await get_auth_context(
            request,
            x_graxia_org_id=str(org_id),
            x_graxia_scopes=None,
        )

        assert "admin:write" not in auth.permissions
        assert "org:read" in auth.permissions

    @pytest.mark.asyncio
    async def test_local_permissions_header_remains_available_for_test_fixtures(self, monkeypatch):
        monkeypatch.setattr("app.auth.dependencies.settings.APP_ENV", "test")
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"x-graxia-permissions", b"admin:write")],
            }
        )

        auth = await get_auth_context(request, x_graxia_scopes=None)

        assert auth.permissions == ["admin:write"]

    @pytest.mark.asyncio
    async def test_staging_matching_header_uses_token_org(self, monkeypatch):
        monkeypatch.setattr("app.auth.dependencies.settings.APP_ENV", "staging")
        org_id = uuid.uuid4()
        request = _request_with_auth_payload({"organization_id": str(org_id)})

        auth = await get_auth_context(
            request,
            x_graxia_org_id=str(org_id),
            x_graxia_scopes=None,
        )

        assert auth.organization_id == org_id
        assert auth.auth_method == "bearer_jwt"
        assert auth.is_mock_auth is False

    @pytest.mark.asyncio
    async def test_staging_mismatched_header_rejected_with_safe_tenant_error(self, monkeypatch):
        monkeypatch.setattr("app.auth.dependencies.settings.APP_ENV", "staging")
        request = _request_with_auth_payload({"organization_id": str(uuid.uuid4())})

        with pytest.raises(HTTPException) as exc_info:
            await get_auth_context(
                request,
                x_graxia_org_id=str(uuid.uuid4()),
                x_graxia_scopes=None,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Resource not found."

    @pytest.mark.asyncio
    async def test_staging_bearer_token_missing_org_rejected(self, monkeypatch):
        monkeypatch.setattr("app.auth.dependencies.settings.APP_ENV", "staging")
        request = _request_with_auth_payload({"sub": "user-1"})

        with pytest.raises(HTTPException) as exc_info:
            await get_auth_context(
                request,
                x_graxia_org_id=str(uuid.uuid4()),
                x_graxia_scopes=None,
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Organization context required."
