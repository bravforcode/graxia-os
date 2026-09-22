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
    ProductReview,
)
from app.models.organization import Organization
from app.models.privacy import BreachNotification, PrivacyConsent
from app.models.referral import ReferralAttribution, ReferralCode, ReferralConversion
from app.models.referral import ReferralPartner
from app.models.skill_conversation import ConversationMessage, ConversationSession
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
async def test_list_consents_is_tenant_scoped(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Consent listing excludes same-user rows from another organization."""
    me = await async_client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    user = (await db_session.execute(
        select(User).where(User.email == me.json()["email"])
    )).scalar_one()
    other_org = Organization(
        id=uuid4(), name=f"Consent Other Org {uuid4()}",
        slug=f"consent-other-{uuid4()}", status="active",
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    db_session.add(other_org)
    await db_session.flush()
    db_session.add(PrivacyConsent(
        id=uuid4(), organization_id=other_org.id, user_id=user.id,
        purpose="foreign-tenant", granted=True,
    ))
    await db_session.commit()

    resp = await async_client.get("/api/v1/privacy/consents")
    assert resp.status_code == 200
    assert "foreign-tenant" not in {c["purpose"] for c in resp.json()}


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
async def test_data_export_is_tenant_scoped(async_client: AsyncClient, db_session: AsyncSession):
    """DSAR export never returns same-email orders from another tenant."""
    me = await async_client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    original_email = me.json()["email"]
    user = (await db_session.execute(select(User).where(User.email == original_email))).scalar_one()
    own_order = FunnelOrder(
        organization_id=user.organization_id,
        customer_email=original_email.upper(),
        subtotal_amount=10,
        total_amount=10,
    )
    other_org = Organization(
        id=uuid4(), name=f"Export Other Org {uuid4()}",
        slug=f"export-other-{uuid4()}", status="active",
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    other_order = FunnelOrder(
        organization_id=other_org.id,
        customer_email=original_email,
        subtotal_amount=20,
        total_amount=20,
    )
    db_session.add(own_order)
    db_session.add(other_org)
    await db_session.flush()
    db_session.add(other_order)
    await db_session.commit()

    resp = await async_client.post("/api/v1/privacy/data-export")
    assert resp.status_code == 200, resp.text
    exported_ids = {row["id"] for row in resp.json()["data"]["orders"]}
    assert str(own_order.id) in exported_ids
    assert str(other_order.id) not in exported_ids


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
    linked_checkout = FunnelCheckoutSession(
        id=uuid4(), organization_id=user.organization_id,
        product_id=product.id, amount=10,
        metadata_json={"unrelated": "checkout-record"},
    )
    db_session.add(linked_checkout)
    await db_session.flush()
    order = FunnelOrder(
        id=uuid4(), organization_id=user.organization_id,
        contact_id=contact.id, user_id=user.id, checkout_session_id=linked_checkout.id,
        stripe_session_id=f"stripe-order-{uuid4()}",
        stripe_payment_intent_id=f"pi-{uuid4()}",
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
    review = ProductReview(
        id=uuid4(), organization_id=user.organization_id, product_id=product.id,
        order_id=order.id, contact_id=contact.id,
        customer_name="Original Customer", customer_email=original_email, rating=5,
    )
    referral_code = ReferralCode(
        id=uuid4(), organization_id=user.organization_id,
        code_hash=uuid4().hex + uuid4().hex, source_type="captured_lead",
        source_id=contact.id, issuer_user_id=user.id,
        owner_identity_hash="identity-hash", audience="regular_user",
        redirect_path="/store",
    )
    partner = ReferralPartner(
        id=uuid4(), organization_id=user.organization_id,
        display_name="Original Partner", user_id=user.id, status="approved",
        commission_rate=0.2,
    )
    db_session.add(partner)
    await db_session.flush()
    referral_code.partner_id = partner.id
    conversation = ConversationSession(
        id=uuid4(), session_key=f"privacy-conversation-{uuid4()}",
        user_id=user.id, title="Private title", description="Private description",
        summary="Private summary", key_entities=["private"],
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    db_session.add(conversation)
    await db_session.flush()
    conversation_message = ConversationMessage(
        id=uuid4(), session_id=conversation.id, message_number=1,
        sender_type="user", sender_id=user.id, content="Private message",
        skill_input={"email": original_email}, skill_output={"secret": "value"},
        context_messages=[1],
        created_at=datetime.now(UTC),
    )
    other_org = Organization(
        id=uuid4(), name=f"Other Privacy Org {uuid4()}",
        slug=f"other-privacy-{uuid4()}", status="active",
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    other_contact = Contact(
        id=uuid4(), organization_id=other_org.id,
        name="Other Tenant Contact", email=original_email,
    )
    other_magnet = LeadMagnet(
        id=uuid4(), organization_id=other_org.id,
        name="Other Tenant Magnet", slug=f"other-magnet-{uuid4()}",
    )
    other_capture = LeadCapture(
        id=uuid4(), organization_id=other_org.id,
        lead_magnet_id=other_magnet.id, email=original_email,
        metadata_json={"email": original_email},
    )
    db_session.add(other_org)
    await db_session.flush()
    db_session.add_all([other_contact, other_magnet])
    await db_session.flush()
    db_session.add_all([
        access, delivery_event, capture, conversion, recommendation, review,
        referral_code, partner, conversation, conversation_message,
        other_capture,
    ])
    await db_session.flush()
    attribution = ReferralAttribution(
        id=uuid4(), organization_id=user.organization_id,
        referral_code_id=referral_code.id, session_id="privacy-referral-session",
        identity_hash="referral-identity-hash",
    )
    referral_conversion = ReferralConversion(
        id=uuid4(), organization_id=user.organization_id,
        referral_code_id=referral_code.id, session_id="privacy-referral-session",
        conversion_key="privacy-conversion-key", verified_order_id=order.id,
        reward_type="regular_bonus", settlement_status="not_applicable",
        gross_amount=0, commission_rate=0, commission_amount=0,
        metadata_json={"email": original_email},
    )
    db_session.add_all([attribution, referral_conversion])
    await db_session.commit()
    checkout_id = checkout.id
    linked_checkout_id = linked_checkout.id
    order_id = order.id
    access_id = access.id
    delivery_event_id = delivery_event.id
    capture_id = capture.id
    contact_id = contact.id
    conversion_id = conversion.id
    recommendation_id = recommendation.id
    review_id = review.id
    referral_code_id = referral_code.id
    attribution_id = attribution.id
    referral_conversion_id = referral_conversion.id
    partner_id = partner.id
    conversation_id = conversation.id
    conversation_message_id = conversation_message.id
    other_contact_id = other_contact.id
    other_capture_id = other_capture.id
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

    linked_checkout = await db_session.get(
        FunnelCheckoutSession, linked_checkout_id
    )
    assert linked_checkout.contact_id is None
    assert linked_checkout.user_id is None
    assert linked_checkout.customer_email is None
    assert linked_checkout.metadata_json is None

    order = await db_session.get(FunnelOrder, order_id)
    assert order.contact_id is None
    assert order.user_id is None
    assert order.checkout_session_id is None
    assert order.stripe_session_id is None
    assert order.stripe_payment_intent_id is None
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

    review = await db_session.get(ProductReview, review_id)
    assert review.customer_name == f"Deleted User {review.id}"
    assert review.customer_email == f"deleted-{review.id}@anonymized.local"
    assert review.order_id is None
    assert review.contact_id is None

    referral_code = await db_session.get(ReferralCode, referral_code_id)
    partner = await db_session.get(ReferralPartner, partner_id)
    assert partner.display_name == f"Deleted Partner {partner.id}"
    assert partner.user_id is None
    assert partner.status == "suspended"
    assert referral_code.partner_id == partner.id
    assert referral_code.issuer_user_id is None
    assert referral_code.owner_identity_hash is None
    assert referral_code.source_id != contact_id

    attribution = await db_session.get(ReferralAttribution, attribution_id)
    assert attribution.identity_hash is None
    assert attribution.session_id == f"deleted-{attribution.id}"

    referral_conversion = await db_session.get(ReferralConversion, referral_conversion_id)
    assert referral_conversion.session_id == f"deleted-{referral_conversion.id}"
    assert referral_conversion.conversion_key == f"deleted-{referral_conversion.id}"
    assert referral_conversion.verified_order_id == order_id
    assert referral_conversion.metadata_json is None

    conversation = await db_session.get(ConversationSession, conversation_id)
    assert conversation.user_id is None
    assert conversation.title is None
    assert conversation.description is None
    assert conversation.summary is None
    assert conversation.key_entities == []
    assert conversation.status == "archived"

    conversation_message = await db_session.get(
        ConversationMessage, conversation_message_id
    )
    assert conversation_message.session_id == conversation_id
    assert conversation_message.sender_id is None
    assert conversation_message.content == "[deleted]"
    assert conversation_message.skill_input is None
    assert conversation_message.skill_output is None
    assert conversation_message.context_messages == []

    other_contact = await db_session.get(Contact, other_contact_id)
    assert other_contact.email == original_email
    other_capture = await db_session.get(LeadCapture, other_capture_id)
    assert other_capture.email == original_email
    assert other_capture.metadata_json == {"email": original_email}


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
