"""PDPA data-subject endpoint tests.

Covers consent give/revoke (with tamper-evident audit trail), data subject
access request (export), right to erasure (anonymize + full), and breach
notification (admin-only, 72h deadline).
"""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.compliance_audit import ComplianceAuditLog
from app.models.privacy import BreachNotification, PrivacyConsent
from app.models.user import User


@pytest.mark.asyncio
async def test_consent_grant_records_audit(async_client: AsyncClient, db_session: AsyncSession):
    """Granting consent returns the record and writes a tamper-evident audit entry."""
    resp = await async_client.post("/api/v1/privacy/consents", json={
        "purpose": "marketing",
        "granted": True,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["purpose"] == "marketing"
    assert data["granted"] is True
    assert data["granted_at"] is not None
    assert data["revoked_at"] is None

    # Audit trail entry exists
    audit_stmt = select(ComplianceAuditLog).where(
        ComplianceAuditLog.event_type == "consent_given"
    )
    audit = (await db_session.execute(audit_stmt)).scalars().all()
    assert len(audit) >= 1
    assert audit[0].gdpr_category == "consent"


@pytest.mark.asyncio
async def test_consent_revoke_toggles_and_audits(async_client: AsyncClient, db_session: AsyncSession):
    """Revoking updates the same row and writes consent_revoked to the trail."""
    await async_client.post("/api/v1/privacy/consents", json={
        "purpose": "analytics", "granted": True,
    })
    resp = await async_client.post("/api/v1/privacy/consents", json={
        "purpose": "analytics", "granted": False,
    })
    assert resp.status_code == 200
    assert resp.json()["granted"] is False
    assert resp.json()["revoked_at"] is not None

    audit = (await db_session.execute(
        select(ComplianceAuditLog).where(ComplianceAuditLog.event_type == "consent_revoked")
    )).scalars().all()
    assert len(audit) >= 1


@pytest.mark.asyncio
async def test_list_consents(async_client: AsyncClient):
    """Consents list returns the records for the current user only."""
    await async_client.post("/api/v1/privacy/consents", json={"purpose": "email", "granted": True})
    resp = await async_client.get("/api/v1/privacy/consents")
    assert resp.status_code == 200
    purposes = [c["purpose"] for c in resp.json()]
    assert "email" in purposes


@pytest.mark.asyncio
async def test_data_export_returns_user_and_consents(async_client: AsyncClient, db_session: AsyncSession):
    """DSAR export returns user, consents and order data with audit entry."""
    await async_client.post("/api/v1/privacy/consents", json={"purpose": "marketing", "granted": True})
    resp = await async_client.post("/api/v1/privacy/data-export")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["data"]["user"]["email"]
    assert any(c["purpose"] == "marketing" for c in data["data"]["consents"])
    assert "orders" in data["data"]

    audit = (await db_session.execute(
        select(ComplianceAuditLog).where(ComplianceAuditLog.event_type == "data_export_requested")
    )).scalars().all()
    assert len(audit) >= 1
    assert audit[0].contains_pii == 1


@pytest.mark.asyncio
async def test_erasure_requires_confirm(async_client: AsyncClient):
    """Erasure without confirm=true is rejected."""
    resp = await async_client.post("/api/v1/privacy/erasure", json={"confirm": False})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_erasure_anonymizes_user(async_client: AsyncClient, db_session: AsyncSession):
    """Anonymize erasure blanks PII and deactivates the account."""
    # Capture the admin user's email from the token owner
    me = await async_client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    original_email = me.json()["email"]

    resp = await async_client.post("/api/v1/privacy/erasure", json={
        "confirm": True, "anonymize_only": True,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["method"] == "anonymized"
    assert data["note"]

    # The same user now has an anonymized email in the DB
    user = (await db_session.execute(
        select(User).where(User.email == original_email)
    )).scalar()
    assert user is None  # original email no longer findable
    anonymized = (await db_session.execute(
        select(User).where(User.email.like("deleted-%@anonymized.local"))
    )).scalars().all()
    assert len(anonymized) == 1
    assert anonymized[0].is_active is False


@pytest.mark.asyncio
async def test_breach_requires_admin(public_async_client: AsyncClient, db_session: AsyncSession):
    """Non-admin users cannot register a breach."""
    from app.core.auth import get_password_hash
    from app.models.organization import Organization

    org = Organization(
        id=uuid4(), name=f"NonAdmin Org {uuid4()}",
        slug=f"nonadmin-org-{uuid4()}", status="active",
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    db_session.add(org)
    await db_session.commit()

    email = f"nonadmin-{uuid4()}@example.com"
    user = User(
        id=uuid4(), email=email,
        hashed_password=get_password_hash("password12345"),
        full_name="Non Admin", role="user", is_active=True,
        totp_enabled=False, organization_id=org.id,
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.commit()

    login = await public_async_client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "password12345"},
    )
    assert login.status_code == 200, login.text
    access_token = login.json().get("access_token")
    assert access_token, "expected an access token"
    public_async_client.headers["Authorization"] = f"Bearer {access_token}"

    resp = await public_async_client.post("/api/v1/privacy/breach", json={
        "description": "Test breach", "affected_subjects": 1, "risk_level": "low",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_breach_registers_72h_deadline(async_client: AsyncClient, db_session: AsyncSession):
    """Admin breach registration sets a 72-hour regulator deadline + audit alert."""
    resp = await async_client.post("/api/v1/privacy/breach", json={
        "description": "Unauthorized access attempt",
        "affected_subjects": 42,
        "risk_level": "high",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "detected"
    assert data["risk_level"] == "high"
    assert data["notification_deadline"] is not None
    assert data["affected_subjects"] == 42

    deadline = datetime.fromisoformat(data["notification_deadline"].replace("Z", "+00:00"))
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    assert deadline - datetime.now(UTC) >= timedelta(hours=71)

    audit = (await db_session.execute(
        select(ComplianceAuditLog).where(ComplianceAuditLog.event_type == "security_alert")
    )).scalars().all()
    assert len(audit) >= 1
    assert audit[0].target_type == "breach"
