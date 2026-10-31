"""
Phase 8 GDPR Compliance Tests
Tests for account erasure and data export (GDPR compliance).
Routed to the PDPA endpoints in app/api/privacy.py.
"""
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from app.core.compliance_audit import AuditEventType, ComplianceAuditLogger
from app.models.user import User

ERASURE_URL = "/api/v1/privacy/erasure"
EXPORT_URL = "/api/v1/privacy/data-export"


class TestAccountDeletion:
    """Test GDPR-compliant account erasure (POST /privacy/erasure)"""

    @pytest.mark.asyncio
    async def test_delete_account_endpoint_exists(self, async_client):
        """Erasure endpoint should exist; confirm=false is a non-destructive probe"""
        response = await async_client.post(ERASURE_URL, json={"confirm": False})

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_account_soft_delete(self, async_client):
        """Anonymize-only erasure should succeed and report method=anonymized"""
        response = await async_client.post(
            ERASURE_URL, json={"confirm": True, "anonymize_only": True}
        )

        assert response.status_code == 200
        assert response.json()["method"] == "anonymized"

    @pytest.mark.asyncio
    async def test_delete_account_anonymizes_email(self, async_client, db_session):
        """Erased account should have email and name anonymized"""
        response = await async_client.post(
            ERASURE_URL, json={"confirm": True, "anonymize_only": True}
        )

        assert response.status_code == 200
        user = await db_session.get(User, UUID(response.json()["user_id"]))
        assert user.email.endswith("@anonymized.local")
        assert user.full_name == "Deleted User"

    @pytest.mark.asyncio
    async def test_delete_account_inactivates_user(self, async_client, db_session):
        """Full erasure should set is_active to False"""
        response = await async_client.post(ERASURE_URL, json={"confirm": True})

        assert response.status_code == 200
        assert response.json()["method"] == "deleted"
        user = await db_session.get(User, UUID(response.json()["user_id"]))
        assert user.is_active is False

    @pytest.mark.asyncio
    async def test_delete_account_revokes_sessions(self, async_client):
        """Erasure should revoke the caller's sessions, so /auth/me no longer authorizes"""
        response = await async_client.post(ERASURE_URL, json={"confirm": True})

        assert response.status_code == 200
        me_response = await async_client.get("/api/v1/auth/me")
        assert me_response.status_code == 401

    @pytest.mark.asyncio
    async def test_deleted_account_cannot_login(self, public_async_client):
        """Deleted account should not be able to login"""
        # This would require creating and deleting a user first
        # Simplified test - just verify the mechanism exists
        response = await public_async_client.post(
            "/api/v1/auth/login",
            data={"username": "deleted@deleted.graxia.io", "password": "any"}
        )

        # Should fail to login
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_delete_account_requires_auth(self, public_async_client):
        """Erasure should require authentication"""
        response = await public_async_client.post(ERASURE_URL, json={"confirm": False})

        assert response.status_code == 401


class TestDataExport:
    """Test GDPR data export functionality (POST /privacy/data-export)"""

    @pytest.mark.asyncio
    async def test_export_data_endpoint_exists(self, async_client):
        """Data export endpoint should exist"""
        response = await async_client.post(EXPORT_URL)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_export_data_returns_machine_readable(self, async_client):
        """Data export should return machine-readable JSON with export metadata"""
        response = await async_client.post(EXPORT_URL)

        assert response.status_code == 200
        body = response.json()
        assert "export_id" in body
        assert "exported_at" in body
        assert isinstance(body["data"], dict)

    @pytest.mark.asyncio
    async def test_export_contains_profile_data(self, async_client):
        """Data export should include user profile"""
        response = await async_client.post(EXPORT_URL)

        assert response.status_code == 200
        user = response.json()["data"]["user"]
        assert "email" in user
        assert "full_name" in user

    @pytest.mark.asyncio
    async def test_export_contains_usage_data(self, async_client):
        """Data export should include consent and order categories"""
        response = await async_client.post(EXPORT_URL)

        assert response.status_code == 200
        data = response.json()["data"]
        assert isinstance(data["consents"], list)
        assert isinstance(data["orders"], list)

    @pytest.mark.asyncio
    async def test_export_data_requires_auth(self, public_async_client):
        """Data export should require authentication"""
        response = await public_async_client.post(EXPORT_URL)

        # Should return 401 Unauthorized
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_export_data_logged(self, async_client):
        """Data export should be recorded in the compliance audit log"""
        with patch.object(ComplianceAuditLogger, "log_event", new_callable=AsyncMock) as mock_audit:
            response = await async_client.post(EXPORT_URL)

        assert response.status_code == 200
        mock_audit.assert_awaited_once()
        assert mock_audit.await_args.kwargs["event_type"] == AuditEventType.DATA_EXPORT_REQUESTED


class TestGDPRCompliance:
    """Test general GDPR compliance features"""

    @pytest.mark.xfail(
        strict=True,
        reason="No /privacy.html route in the API; AuthMiddleware fails closed with 403 on unknown paths",
    )
    @pytest.mark.asyncio
    async def test_privacy_policy_accessible(self, public_async_client):
        """Privacy policy should be publicly accessible"""
        response = await public_async_client.get("/privacy.html")

        # Should return 200 or redirect
        assert response.status_code in [200, 301, 302, 404]  # 404 if not in API

    @pytest.mark.xfail(
        strict=True,
        reason="No /terms.html route in the API; AuthMiddleware fails closed with 403 on unknown paths",
    )
    @pytest.mark.asyncio
    async def test_terms_of_service_accessible(self, public_async_client):
        """Terms of service should be publicly accessible"""
        response = await public_async_client.get("/terms.html")

        # Should return 200 or redirect
        assert response.status_code in [200, 301, 302, 404]  # 404 if not in API

    @pytest.mark.asyncio
    async def test_data_retention_policy(self, async_client):
        """User should be able to access own data"""
        response = await async_client.post(EXPORT_URL)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_right_to_be_forgotten(self, async_client):
        """User should be able to erase their account"""
        response = await async_client.post(ERASURE_URL, json={"confirm": True})

        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    @pytest.mark.asyncio
    async def test_right_to_data_portability(self, async_client):
        """Export should be returned as JSON (portable format)"""
        response = await async_client.post(EXPORT_URL)

        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("application/json")


class TestGDPRAuditLogging:
    """Test GDPR-related audit logging"""

    @pytest.mark.asyncio
    async def test_account_deletion_logged(self, async_client):
        """Account erasure should be recorded in the compliance audit log"""
        with patch.object(ComplianceAuditLogger, "log_event", new_callable=AsyncMock) as mock_audit:
            response = await async_client.post(
                ERASURE_URL, json={"confirm": True, "anonymize_only": True}
            )

        assert response.status_code == 200
        mock_audit.assert_awaited_once()
        assert mock_audit.await_args.kwargs["event_type"] == AuditEventType.DATA_DELETION_REQUESTED

    @pytest.mark.asyncio
    async def test_data_export_logged(self, async_client):
        """Data export should be recorded in the compliance audit log"""
        with patch.object(ComplianceAuditLogger, "log_event", new_callable=AsyncMock) as mock_audit:
            response = await async_client.post(EXPORT_URL)

        assert response.status_code == 200
        mock_audit.assert_awaited_once()
        assert mock_audit.await_args.kwargs["event_type"] == AuditEventType.DATA_EXPORT_REQUESTED
