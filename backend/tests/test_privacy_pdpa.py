"""PDPA data-subject endpoint tests.

Covers consent give/revoke (with tamper-evident audit trail), data subject
access request (export), right to erasure (anonymize + full), and breach
notification (admin-only, 72h deadline).
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.compliance_audit import ComplianceAuditLog
from app.models.contact import Contact
from app.models.funnel import (
    ConversionEvent,
    DeliveryAccess,
    DeliveryEmailEvent,
    DigitalProduct,
    FunnelCheckoutSession,
    FunnelOrder,
    FunnelRecommendation,
    LeadCapture,
    LeadMagnet,
)
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
async def test_erasure_deletes_user_consents(async_client: AsyncClient, db_session: AsyncSession):
    """Full erasure scrubs sensitive fields while preserving FK/audit rows."""
    me = await async_client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    original_email = me.json()["email"]
    user = (await db_session.execute(
        select(User).where(User.email == original_email)
    )).scalar_one()
    product = DigitalProduct(
        id=uuid4(), organization_id=user.organization_id,
        name="Privacy Test Product", slug=f"privacy-{uuid4()}",
        price_amount=10, product_type="ebook",
    )
    contact = Contact(
        id=uuid4(), organization_id=user.organization_id,
        name="Original Contact", email=original_email,
        company="PII Company", notes="PII notes", marketing_consent=True,
        marketing_consent_at=datetime.now(UTC), consent_version="v1",
    )
    lead_magnet = LeadMagnet(
        id=uuid4(), organization_id=user.organization_id,
        name="Privacy Test Magnet", slug=f"privacy-magnet-{uuid4()}",
    )
    db_session.add_all([product, contact, lead_magnet])
    await db_session.flush()
    checkout = FunnelCheckoutSession(
        id=uuid4(), organization_id=user.organization_id,
        product_id=product.id, contact_id=contact.id, user_id=user.id,
        stripe_session_id=f"stripe-{uuid4()}", customer_email=original_email,
        amount=10, metadata_json={"email": original_email},
    )
    db_session.add(checkout)
    await db_session.flush()
    order = FunnelOrder(
        id=uuid4(), organization_id=user.organization_id,
        contact_id=contact.id, user_id=user.id, checkout_session_id=checkout.id,
        customer_email=original_email, subtotal_amount=10, total_amount=10,
    )
    db_session.add(order)
    await db_session.flush()
    access = DeliveryAccess(
        id=uuid4(), organization_id=user.organization_id,
        order_id=order.id, product_id=product.id, contact_id=contact.id,
        access_token_hash="secret-token-hash", metadata_json={"email": original_email},
    )
    delivery_event = DeliveryEmailEvent(
        id=uuid4(), organization_id=user.organization_id, order_id=order.id,
        delivery_access_id=access.id, customer_email=original_email,
        idempotency_key=f"delivery-{uuid4()}", metadata_json={"email": original_email},
    )
    capture = LeadCapture(
        id=uuid4(), organization_id=user.organization_id,
        lead_magnet_id=lead_magnet.id, email=original_email,
        metadata_json={"email": original_email},
    )
    conversion = ConversionEvent(
        id=uuid4(), organization_id=user.organization_id, event_type="purchase",
        contact_id=contact.id, order_id=order.id, session_id=str(checkout.id),
        idempotency_key=f"conversion-{uuid4()}", source="email",
        metadata_json={"email": original_email},
    )
    recommendation = FunnelRecommendation(
        id=uuid4(), organization_id=user.organization_id, product_id=product.id,
        recommendation_type="test", recommended_action="Test action",
        metadata_json={"email": original_email},
    )
    db_session.add_all([access, delivery_event, capture, conversion, recommendation])
    await db_session.commit()
    checkout_id = checkout.id
    order_id = order.id
    access_id = access.id
    delivery_event_id = delivery_event.id
    capture_id = capture.id
    contact_id = contact.id
    conversion_id = conversion.id
    recommendation_id = recommendation.id
    db_session.expire_all()

    consent = await async_client.post(
        "/api/v1/privacy/consents",
        json={"purpose": "full-erasure", "granted": True},
    )
    assert consent.status_code == 200, consent.text

    resp = await async_client.post(
        "/api/v1/privacy/erasure",
        json={"confirm": True},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["method"] == "scrubbed"
    remaining = (
        await db_session.execute(
            select(PrivacyConsent).where(PrivacyConsent.purpose == "full-erasure")
        )
    ).scalars().all()
    assert remaining == []

    user = await db_session.get(User, UUID(resp.json()["user_id"]))
    assert user is not None
    assert user.email != original_email
    assert user.email == f"deleted-{user.id}@anonymized.local"
    assert user.full_name is None
    assert user.hashed_password == "!deleted!"
    assert user.last_login_at is None
    assert user.totp_secret is None
    assert user.totp_enabled is False
    assert user.provider is None
    assert user.provider_id is None
    assert user.avatar_url is None
    assert user.onboarding_completed_at is None
    assert user.is_active is False

    checkout = await db_session.get(FunnelCheckoutSession, checkout_id)
    assert checkout.contact_id is None
    assert checkout.user_id is None
    assert checkout.customer_email is None
    assert checkout.stripe_session_id is None
    assert checkout.metadata_json is None

    order = await db_session.get(FunnelOrder, order_id)
    assert order.contact_id is None
    assert order.user_id is None
    assert order.checkout_session_id is None
    assert order.customer_email is None

    access = await db_session.get(DeliveryAccess, access_id)
    assert access.contact_id is None
    assert access.access_token_hash is None
    assert access.metadata_json is None

    delivery_event = await db_session.get(DeliveryEmailEvent, delivery_event_id)
    assert delivery_event.customer_email == f"deleted-{delivery_event.id}@anonymized.local"
    assert delivery_event.delivery_access_id is None
    assert delivery_event.metadata_json is None

    capture = await db_session.get(LeadCapture, capture_id)
    assert capture.email == f"deleted-{capture.id}@anonymized.local"
    assert capture.metadata_json is None

    contact = await db_session.get(Contact, contact_id)
    assert contact.name == f"Deleted Contact {contact.id}"
    assert contact.email is None
    assert contact.company is None
    assert contact.notes is None
    assert contact.marketing_consent is False
    assert contact.marketing_consent_at is None
    assert contact.consent_version is None
    assert contact.is_deleted is True

    conversion = await db_session.get(ConversionEvent, conversion_id)
    assert conversion.contact_id is None
    assert conversion.order_id is None
    assert conversion.session_id is None
    assert conversion.idempotency_key is None
    assert conversion.source is None
    assert conversion.metadata_json is None

    recommendation = await db_session.get(FunnelRecommendation, recommendation_id)
    assert recommendation.metadata_json is None


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
