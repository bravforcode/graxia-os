from __future__ import annotations

from decimal import Decimal
from uuid import UUID
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.api.funnel import submit_recommendation_for_approval
from app.auth.context import AuthContext
from app.models.funnel import DigitalProduct, FunnelCheckoutSession
from app.runtime.events import business_event_repository
from app.services.funnel_service import (
    delivery_access_service,
    funnel_recommendation_service,
    funnel_webhook_handler,
    lead_magnet_service,
)
from tests.factories import OrganizationFactory


@pytest.fixture(autouse=True)
async def _clear_business_events():
    await business_event_repository.clear()
    yield
    await business_event_repository.clear()


@pytest.mark.asyncio
async def test_checkout_completed_emits_payment_order_and_delivery_events(db_session):
    org = await OrganizationFactory.build(db_session)
    product = DigitalProduct(
        id=uuid4(),
        organization_id=org.id,
        name="Event Product",
        slug="event-product",
        price_amount=Decimal("99"),
        status="published",
    )
    db_session.add(product)
    await db_session.commit()

    checkout = FunnelCheckoutSession(
        id=uuid4(),
        organization_id=org.id,
        product_id=product.id,
        amount=Decimal("99"),
        currency="THB",
        status="completed",
        customer_email="buyer@test.com",
    )
    db_session.add(checkout)
    await db_session.commit()

    result = await funnel_webhook_handler.handle_checkout_completed(
        organization_id=org.id,
        checkout_session_id=checkout.id,
        customer_email="buyer@test.com",
        db=db_session,
    )
    assert result["duplicate"] is False

    events = await business_event_repository.list(organization_id=str(org.id))
    event_types = [event.event_type for event in events]
    assert "payment.succeeded" in event_types
    assert "order.created" in event_types
    assert "delivery.access.granted" in event_types
    for event in events:
        assert "token" not in str(event.payload).lower()


@pytest.mark.asyncio
async def test_delivery_open_emits_business_event(db_session):
    org = await OrganizationFactory.build(db_session)
    product = DigitalProduct(id=uuid4(), organization_id=org.id, name="Open", slug="open", price_amount=Decimal("10"))
    db_session.add(product)
    await db_session.commit()

    checkout = FunnelCheckoutSession(
        id=uuid4(),
        organization_id=org.id,
        product_id=product.id,
        amount=Decimal("10"),
        currency="THB",
        status="completed",
        customer_email="open@test.com",
    )
    db_session.add(checkout)
    await db_session.commit()
    result = await funnel_webhook_handler.handle_checkout_completed(
        organization_id=org.id,
        checkout_session_id=checkout.id,
        customer_email="open@test.com",
        db=db_session,
    )

    await business_event_repository.clear()
    access = await delivery_access_service.get_access_by_id(UUID(result["access_id"]), org.id, db=db_session)
    opened = await delivery_access_service.record_open(access.id, db=db_session)
    assert opened.open_count == 1

    events = await business_event_repository.list(event_type="delivery.opened")
    assert len(events) == 1
    assert events[0].subject_id == str(access.id)


@pytest.mark.asyncio
async def test_lead_capture_emits_only_once_for_duplicate(db_session):
    org = await OrganizationFactory.build(db_session)
    magnet = await lead_magnet_service.create(
        organization_id=org.id,
        slug="event-guide",
        title="Event Guide",
        db=db_session,
    )
    first = await lead_magnet_service.capture(
        lead_magnet_id=magnet.id,
        organization_id=org.id,
        email="lead@test.com",
        source="landing-page",
        db=db_session,
    )
    second = await lead_magnet_service.capture(
        lead_magnet_id=magnet.id,
        organization_id=org.id,
        email="lead@test.com",
        source="landing-page",
        db=db_session,
    )
    assert first is not None
    assert second is None

    events = await business_event_repository.list(event_type="lead.captured")
    assert len(events) == 1
    assert events[0].payload["email_domain"] == "test.com"


@pytest.mark.asyncio
async def test_recommendation_create_emits_business_event(db_session):
    org = await OrganizationFactory.build(db_session)
    product = DigitalProduct(id=uuid4(), organization_id=org.id, name="Reco", slug="reco", price_amount=Decimal("50"))
    db_session.add(product)
    await db_session.commit()

    rec = await funnel_recommendation_service.create(
        organization_id=org.id,
        product_id=product.id,
        recommendation_type="headline_change",
        recommended_action="Tighten headline",
        confidence="high",
        effort="low",
        risk="low",
        db=db_session,
    )
    events = await business_event_repository.list(event_type="recommendation.created")
    assert len(events) == 1
    assert events[0].subject_id == str(rec.id)


@pytest.mark.asyncio
async def test_submit_recommendation_for_approval_emits_approval_requested(db_session):
    org = await OrganizationFactory.build(db_session)
    product = DigitalProduct(id=uuid4(), organization_id=org.id, name="Approval", slug="approval", price_amount=Decimal("120"))
    db_session.add(product)
    await db_session.commit()
    rec = await funnel_recommendation_service.create(
        organization_id=org.id,
        product_id=product.id,
        recommendation_type="price_test",
        recommended_action="Test 490 THB",
        db=db_session,
    )
    await business_event_repository.clear()

    auth = AuthContext(
        actor_type="system",
        actor_id="test-suite",
        organization_id=org.id,
        environment="test",
        is_mock_auth=True,
    )
    result = await submit_recommendation_for_approval(
        rec_id=rec.id,
        auth=auth,
        organization_id=org.id,
        db=db_session,
    )
    assert result["status"] == "submitted"

    events = await business_event_repository.list(event_type="approval.requested")
    assert len(events) == 1
    assert events[0].payload["recommendation_id"] == str(rec.id)
