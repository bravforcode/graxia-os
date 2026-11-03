"""Offline regression tests for scoped, signed marketing opt-out proofs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from unittest.mock import AsyncMock

import pytest
import jwt

from app.config import settings
from app.models.contact import Contact
from app.models.funnel import DeliveryAccess, DigitalProduct, FunnelOrder
from app.models.organization import Organization
from app.services import automation_email_service
from app.services.email_service import EmailService, _sent_keys
from app.services.funnel_delivery_email_service import (
    DeliveryEmailOutcome,
    FunnelDeliveryEmailService,
)
from app.services.unsubscribe_tokens import (
    UnsubscribeProofUnavailable,
    create_unsubscribe_token,
    create_unsubscribe_url,
    verify_unsubscribe_token,
)


def _contact(organization_id, email: str) -> Contact:
    return Contact(
        id=uuid4(),
        organization_id=organization_id,
        name="Opted In",
        email=email,
        contact_type="lead",
        relationship_strength=1,
        marketing_consent=True,
        marketing_consent_at=datetime.now(UTC),
        consent_version="organic-v1",
    )


def _tamper(token: str) -> str:
    header, payload, signature = token.split(".")
    first = "A" if signature[0] != "A" else "B"
    return f"{header}.{payload}.{first}{signature[1:]}"


def _expired_token(organization_id, email: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "type": "unsubscribe",
            "purpose": "marketing_unsubscribe",
            "organization_id": str(organization_id),
            "email": email.lower(),
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        },
        settings.ACTIVE_JWT_SIGNING_KEY,
        algorithm="HS256",
        headers={"kid": settings.JWT_ACTIVE_KID},
    )


def test_unsubscribe_proof_expiry_is_365_days():
    token = create_unsubscribe_token(uuid4(), "customer@example.com")
    payload = jwt.decode(token, options={"verify_signature": False})

    assert payload["exp"] - payload["iat"] == int(timedelta(days=365).total_seconds())


@pytest.mark.asyncio
async def test_get_confirmation_is_read_only_then_post_confirms(
    public_async_client, db_session
):
    org = Organization(
        id=uuid4(), name="Unsubscribe Org", slug=f"unsubscribe-{uuid4().hex}"
    )
    contact = _contact(org.id, "stop@example.com")
    db_session.add(org)
    await db_session.flush()
    db_session.add(contact)
    await db_session.commit()
    token = create_unsubscribe_token(org.id, contact.email)

    preview = await public_async_client.get(
        "/api/v1/public/funnel/unsubscribe", params={"token": token}
    )

    assert preview.status_code == 200
    assert 'method="post"' in preview.text
    assert token in preview.text
    await db_session.refresh(contact)
    assert contact.marketing_unsubscribed is False

    confirmed = await public_async_client.post(
        "/api/v1/public/funnel/unsubscribe/confirm", data={"token": token}
    )

    assert confirmed.status_code == 200
    await db_session.refresh(contact)
    assert contact.marketing_unsubscribed is True
    assert contact.marketing_unsubscribed_at is not None


@pytest.mark.asyncio
async def test_json_unsubscribe_rejects_unsigned_expired_and_tampered_proofs(
    public_async_client, db_session
):
    org = Organization(
        id=uuid4(), name="Token Org", slug=f"token-org-{uuid4().hex}"
    )
    contact = _contact(org.id, "stop@example.com")
    db_session.add(org)
    await db_session.flush()
    db_session.add(contact)
    await db_session.commit()

    unsigned = await public_async_client.post(
        "/api/v1/public/funnel/unsubscribe",
        json={"organization_id": str(org.id), "email": contact.email},
    )
    assert unsigned.status_code == 422

    expired = _expired_token(org.id, contact.email)
    tampered = _tamper(create_unsubscribe_token(org.id, contact.email))
    for token in (expired, tampered):
        response = await public_async_client.post(
            "/api/v1/public/funnel/unsubscribe", json={"token": token}
        )
        assert response.status_code == 401

    await db_session.refresh(contact)
    assert contact.marketing_unsubscribed is False


@pytest.mark.asyncio
async def test_valid_proof_only_unsubscribes_its_organization_and_email(
    public_async_client, db_session
):
    victim_org = Organization(
        id=uuid4(), name="Victim Org", slug=f"victim-{uuid4().hex}"
    )
    token_org = Organization(
        id=uuid4(), name="Token Org", slug=f"token-{uuid4().hex}"
    )
    victim = _contact(victim_org.id, "victim@example.com")
    token_contact = _contact(token_org.id, "OWNER@Example.com")
    db_session.add_all([victim_org, token_org])
    await db_session.flush()
    db_session.add_all([victim, token_contact])
    await db_session.commit()
    token = create_unsubscribe_token(token_org.id, " owner@example.com ")

    response = await public_async_client.post(
        "/api/v1/public/funnel/unsubscribe", json={"token": token}
    )

    assert response.status_code == 200
    await db_session.refresh(victim)
    await db_session.refresh(token_contact)
    assert victim.marketing_unsubscribed is False
    assert token_contact.marketing_unsubscribed is True
    assert verify_unsubscribe_token(token) == (token_org.id, "owner@example.com")


@pytest.mark.asyncio
async def test_missing_signing_key_fails_closed_without_contact_mutation(
    public_async_client, db_session, monkeypatch
):
    org = Organization(
        id=uuid4(), name="Unavailable Org", slug=f"unavailable-{uuid4().hex}"
    )
    contact = _contact(org.id, "stop@example.com")
    db_session.add(org)
    await db_session.flush()
    db_session.add(contact)
    await db_session.commit()
    token = create_unsubscribe_token(org.id, contact.email)
    monkeypatch.setattr(settings, "JWT_SIGNING_KEYS", '{"v1": ""}')

    response = await public_async_client.post(
        "/api/v1/public/funnel/unsubscribe", json={"token": token}
    )

    assert response.status_code == 503
    await db_session.refresh(contact)
    assert contact.marketing_unsubscribed is False
    with pytest.raises(UnsubscribeProofUnavailable):
        create_unsubscribe_url(org.id, contact.email)


@pytest.mark.asyncio
async def test_automation_sender_adds_signed_scoped_unsubscribe_link(
    db_session, monkeypatch
):
    send_email = AsyncMock(return_value={"id": "offline", "status": "accepted"})
    monkeypatch.setattr(
        automation_email_service, "email_service", SimpleNamespace(send_email=send_email)
    )
    org = Organization(
        id=uuid4(), name="Automation Test", slug=f"automation-{uuid4().hex}"
    )
    contact = _contact(org.id, " customer@EXAMPLE.com ")
    db_session.add(org)
    await db_session.flush()
    db_session.add(contact)
    await db_session.flush()

    result = await automation_email_service.AutomationEmailService(db_session)._send(
        organization_id=org.id,
        to="Customer@Example.com",
        template_name="funnel_automation_welcome",
        template_data={"to_name": "Customer", "store_url": "https://store.example"},
        idempotency_key="offline-unsubscribe-link",
    )

    assert result["status"] == "accepted"
    sent = send_email.await_args.kwargs
    assert "organization_id" not in sent
    link = sent["template_data"]["unsubscribe_url"]
    token = parse_qs(urlparse(link).query)["token"][0]
    assert verify_unsubscribe_token(token) == (org.id, "customer@example.com")

    send_email.reset_mock()
    monkeypatch.setattr(settings, "JWT_SIGNING_KEYS", '{"v1": ""}')
    suppressed = await automation_email_service.AutomationEmailService(
        db_session
    )._send(
        organization_id=org.id,
        marketing_contact_id=contact.id,
        to="Customer@Example.com",
        template_name="funnel_automation_welcome",
        template_data={"to_name": "Customer", "store_url": "https://store.example"},
        idempotency_key="offline-unsubscribe-link-unavailable",
    )
    assert suppressed["status"] == "suppressed"
    send_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_automation_sender_suppresses_mismatched_contact_recipient(
    db_session, monkeypatch
):
    send_email = AsyncMock(return_value={"id": "offline", "status": "accepted"})
    monkeypatch.setattr(
        automation_email_service, "email_service", SimpleNamespace(send_email=send_email)
    )
    org = Organization(
        id=uuid4(), name="Automation Test", slug=f"automation-{uuid4().hex}"
    )
    contact = _contact(org.id, "opted-in@example.com")
    db_session.add(org)
    await db_session.flush()
    db_session.add(contact)
    await db_session.flush()

    result = await automation_email_service.AutomationEmailService(db_session)._send(
        organization_id=org.id,
        marketing_contact_id=contact.id,
        to="different-recipient@example.com",
        template_name="funnel_automation_welcome",
        template_data={"to_name": "Customer"},
        idempotency_key="offline-mismatched-recipient",
    )

    assert result["status"] == "suppressed"
    send_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_automation_sender_suppresses_missing_marketing_consent(
    db_session, monkeypatch
):
    send_email = AsyncMock(return_value={"id": "offline", "status": "accepted"})
    monkeypatch.setattr(
        automation_email_service, "email_service", SimpleNamespace(send_email=send_email)
    )
    org = Organization(
        id=uuid4(), name="Automation Test", slug=f"automation-{uuid4().hex}"
    )
    contact = _contact(org.id, "customer@example.com")
    contact.marketing_consent = False
    db_session.add(org)
    await db_session.flush()
    db_session.add(contact)
    await db_session.flush()

    result = await automation_email_service.AutomationEmailService(db_session)._send(
        organization_id=org.id,
        marketing_contact_id=contact.id,
        to="customer@example.com",
        template_name="funnel_automation_welcome",
        template_data={"to_name": "Customer"},
        idempotency_key="offline-missing-consent",
    )

    assert result["status"] == "suppressed"
    send_email.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_field", "status_value"),
    [("marketing_unsubscribed", True), ("is_deleted", True)],
    ids=["unsubscribed", "soft-deleted"],
)
async def test_automation_sender_suppresses_ineligible_contact_status(
    db_session, monkeypatch, status_field, status_value
):
    send_email = AsyncMock(return_value={"id": "offline", "status": "accepted"})
    monkeypatch.setattr(
        automation_email_service, "email_service", SimpleNamespace(send_email=send_email)
    )
    org = Organization(
        id=uuid4(), name="Automation Test", slug=f"automation-{uuid4().hex}"
    )
    contact = _contact(org.id, "customer@example.com")
    setattr(contact, status_field, status_value)
    db_session.add(org)
    await db_session.flush()
    db_session.add(contact)
    await db_session.flush()

    result = await automation_email_service.AutomationEmailService(db_session)._send(
        organization_id=org.id,
        marketing_contact_id=contact.id,
        to="customer@example.com",
        template_name="funnel_automation_welcome",
        template_data={"to_name": "Customer"},
        idempotency_key=f"offline-{status_field}",
    )

    assert result["status"] == "suppressed"
    send_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_transactional_delivery_uses_persisted_order_recipient_without_opt_in(
    db_session, monkeypatch
):
    send_email = AsyncMock(return_value={"id": "provider-reference-1", "status": "sent"})
    monkeypatch.setattr(
        "app.services.funnel_delivery_email_service.email_service",
        SimpleNamespace(send_email=send_email),
    )
    org = Organization(
        id=uuid4(), name="Delivery Test", slug=f"delivery-{uuid4().hex}"
    )
    contact = _contact(org.id, "buyer@example.com")
    contact.marketing_consent = False
    db_session.add(org)
    await db_session.flush()
    db_session.add(contact)
    await db_session.flush()
    product = DigitalProduct(
        id=uuid4(), organization_id=org.id, name="Synthetic Product",
        slug=f"synthetic-{uuid4().hex}", status="published",
        price_amount=Decimal("10.00"), currency="USD",
    )
    order = FunnelOrder(
        id=uuid4(), organization_id=org.id, contact_id=contact.id,
        status="paid", subtotal_amount=Decimal("10.00"),
        total_amount=Decimal("10.00"), currency="USD",
        customer_email="buyer@example.com",
    )
    access = DeliveryAccess(
        id=uuid4(), organization_id=org.id, order_id=order.id,
        product_id=product.id, status="active", access_token_hash="offline-hash",
    )
    db_session.add(product)
    await db_session.flush()
    db_session.add(order)
    await db_session.flush()
    db_session.add(access)
    await db_session.flush()
    attempt_store = SimpleNamespace(
        claim=AsyncMock(return_value=SimpleNamespace(acquired=True)),
        finish=AsyncMock(),
    )
    service = FunnelDeliveryEmailService(db_session, attempt_store=attempt_store)

    outcome = await service.send_delivery_links(
        org.id, order.id, order.customer_email, [(access, "offline-token")]
    )

    assert outcome == DeliveryEmailOutcome("sent", "provider-reference-1")
    send_email.assert_awaited_once()

    send_email.reset_mock()
    mismatch = await service.send_delivery_links(
        org.id, order.id, "different-recipient@example.com", [(access, "offline-token")]
    )
    assert mismatch.status == "suppressed"
    send_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_purchase_promo_is_suppressed_without_consent(
    db_session, monkeypatch
):
    send_email = AsyncMock(return_value={"id": "offline", "status": "accepted"})
    monkeypatch.setattr(
        automation_email_service, "email_service", SimpleNamespace(send_email=send_email)
    )
    org = Organization(
        id=uuid4(), name="Post-Purchase Test", slug=f"post-purchase-{uuid4().hex}"
    )
    contact = _contact(org.id, "buyer@example.com")
    contact.marketing_consent = False
    db_session.add(org)
    await db_session.flush()
    db_session.add(contact)
    await db_session.flush()
    order = FunnelOrder(
        id=uuid4(), organization_id=org.id, contact_id=contact.id,
        status="paid", subtotal_amount=Decimal("10.00"),
        total_amount=Decimal("10.00"), currency="USD",
        customer_email="buyer@example.com",
    )
    db_session.add(order)
    await db_session.flush()

    result = await automation_email_service.AutomationEmailService(
        db_session
    ).trigger_post_purchase(org.id, order.id)

    assert result["status"] == "suppressed"
    send_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_automation_email_footer_is_required_and_rendered_without_network(
    monkeypatch,
):
    service = EmailService()
    provider_send = AsyncMock(
        return_value={"id": "offline", "status": "accepted"}
    )
    monkeypatch.setattr(service, "_real_email_send_allowed", lambda _to: True)
    monkeypatch.setattr(service, "_send_via_resend", provider_send)
    _sent_keys.clear()
    unsubscribe_url = create_unsubscribe_url(uuid4(), "customer@example.com")

    result = await service.send_email(
        to="customer@example.com",
        template_name="funnel_automation_welcome",
        template_data={
            "to_name": "Customer",
            "store_url": "https://store.example",
            "unsubscribe_url": unsubscribe_url,
        },
        idempotency_key="offline-footer-with-proof",
    )

    assert result["status"] == "sent"
    params = provider_send.await_args.args[0]
    assert unsubscribe_url in params["html"]
    assert unsubscribe_url in params["text"]
    assert params["html"].index("Unsubscribe") < params["html"].lower().rfind("</body>")

    provider_send.reset_mock()
    _sent_keys.clear()
    suppressed = await service.send_email(
        to="customer@example.com",
        template_name="funnel_automation_welcome",
        template_data={"to_name": "Customer", "store_url": "https://store.example"},
        idempotency_key="offline-footer-without-proof",
    )

    assert suppressed["status"] == "suppressed"
    provider_send.assert_not_awaited()
    _sent_keys.clear()
