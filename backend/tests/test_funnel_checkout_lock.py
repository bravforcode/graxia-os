from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.funnel import (
    DeliveryAccess,
    DeliveryAsset,
    DigitalProduct,
    FunnelCheckoutSession,
    FunnelOrder,
    FunnelOrderItem,
)
from tests.factories import OrganizationFactory


@pytest.fixture
def enable_test_checkout_simulation(monkeypatch):
    monkeypatch.setattr(settings, "TESTING", True)
    monkeypatch.setattr(settings, "APP_ENV", "testing")


@pytest.mark.asyncio
async def test_order_service_rejects_stripe_session_mismatch(
    db_session: AsyncSession,
):
    from app.services.funnel_order_service import FunnelOrderService

    org = await OrganizationFactory.build(db_session)
    product = DigitalProduct(
        id=uuid4(),
        organization_id=org.id,
        name="P",
        slug="p-webhook-session-mismatch",
        price_amount=Decimal("20.00"),
        currency="THB",
        status="published",
    )
    checkout = FunnelCheckoutSession(
        id=uuid4(),
        organization_id=org.id,
        product_id=product.id,
        stripe_session_id="cs_expected_webhook",
        status="pending",
        amount=Decimal("20.00"),
        currency="THB",
    )
    db_session.add_all([product, checkout])
    await db_session.commit()
    checkout_id = checkout.id

    result = await FunnelOrderService(db_session).create_order_from_checkout_completed(
        {
            "id": "cs_wrong_webhook",
            "metadata": {
                "organization_id": str(org.id),
                "product_id": str(product.id),
                "funnel_checkout_session_id": str(checkout.id),
            },
        }
    )

    assert result is None
    assert await db_session.scalar(
        select(FunnelOrder.id).where(FunnelOrder.checkout_session_id == checkout_id)
    ) is None
    await db_session.refresh(checkout)
    assert checkout.status == "pending"


@pytest.mark.asyncio
async def test_order_service_sequential_replay_with_zero_assets_is_idempotent(
    db_session: AsyncSession,
):
    from app.services.funnel_order_service import FunnelOrderService
    from app.services.funnel_delivery_email_service import DeliveryEmailOutcome

    org = await OrganizationFactory.build(db_session)
    product = DigitalProduct(
        id=uuid4(),
        organization_id=org.id,
        name="P",
        slug="p-webhook-zero-assets",
        price_amount=Decimal("20.00"),
        currency="THB",
        status="published",
    )
    checkout = FunnelCheckoutSession(
        id=uuid4(),
        organization_id=org.id,
        product_id=product.id,
        stripe_session_id="cs_zero_assets",
        status="pending",
        amount=Decimal("20.00"),
        currency="THB",
    )
    db_session.add_all([product, checkout])
    await db_session.commit()
    checkout_id = checkout.id
    event = {
        "id": "cs_zero_assets",
        "metadata": {
            "organization_id": str(org.id),
            "product_id": str(product.id),
            "funnel_checkout_session_id": str(checkout.id),
        },
    }

    with patch(
        "app.services.funnel_delivery_email_service.FunnelDeliveryEmailService.send_delivery_links",
        new_callable=AsyncMock,
        return_value=DeliveryEmailOutcome("suppressed"),
    ) as send_delivery, patch(
        "app.services.automation_email_service.AutomationEmailService.trigger_post_purchase",
        new_callable=AsyncMock,
    ):
        first = await FunnelOrderService(db_session).create_order_from_checkout_completed(event)
        second = await FunnelOrderService(db_session).create_order_from_checkout_completed(event)

    assert first is not None
    assert second is not None
    assert first.id == second.id
    send_delivery.assert_awaited_once()
    assert await db_session.scalar(
        select(func.count()).select_from(FunnelOrder).where(
            FunnelOrder.checkout_session_id == checkout_id
        )
    ) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(FunnelOrderItem).where(
            FunnelOrderItem.order_id == first.id
        )
    ) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(DeliveryAccess).where(
            DeliveryAccess.order_id == first.id
        )
    ) == 0


@pytest.mark.asyncio
async def test_simulated_checkout_rejects_mismatched_stripe_session(
    db_session: AsyncSession, enable_test_checkout_simulation,
):
    from app.services.funnel_service import FunnelWebhookHandler

    org = await OrganizationFactory.build(db_session)
    organization_id = org.id
    product = DigitalProduct(
        id=uuid4(),
        organization_id=org.id,
        name="P",
        slug="p-sim-session-mismatch",
        price_amount=Decimal("20.00"),
        currency="THB",
        status="published",
    )
    checkout = FunnelCheckoutSession(
        id=uuid4(),
        organization_id=org.id,
        product_id=product.id,
        stripe_session_id="cs_persisted_simulation",
        status="pending",
        amount=Decimal("20.00"),
        currency="THB",
    )
    db_session.add_all([product, checkout])
    await db_session.commit()
    checkout_id = checkout.id

    with pytest.raises(ValueError, match="does not match"):
        await FunnelWebhookHandler().handle_checkout_completed(
            organization_id=organization_id,
            checkout_session_id=checkout_id,
            customer_email="fixture@example.invalid",
            stripe_session_id="cs_wrong_simulation",
            db=db_session,
        )

    assert await db_session.scalar(
        select(FunnelOrder.id).where(FunnelOrder.checkout_session_id == checkout_id)
    ) is None
    assert await db_session.scalar(
        select(func.count()).select_from(DeliveryAccess).where(
            DeliveryAccess.organization_id == organization_id
        )
    ) == 0


@pytest.mark.asyncio
async def test_simulated_checkout_is_sequentially_idempotent_and_mocked(
    db_session: AsyncSession, enable_test_checkout_simulation,
):
    from app.services.funnel_service import FunnelWebhookHandler

    org = await OrganizationFactory.build(db_session)
    product = DigitalProduct(
        id=uuid4(),
        organization_id=org.id,
        name="P",
        slug="p-sim-idempotent",
        price_amount=Decimal("25.00"),
        currency="THB",
        status="published",
    )
    checkout = FunnelCheckoutSession(
        id=uuid4(),
        organization_id=org.id,
        product_id=product.id,
        stripe_session_id="cs_sim_idempotent",
        status="pending",
        amount=Decimal("25.00"),
        currency="THB",
    )
    db_session.add_all([product, checkout])
    await db_session.commit()

    with patch(
        "app.services.funnel_service.mock_email_provider.send_delivery_email",
        new_callable=AsyncMock,
    ) as mock_send, patch(
        "app.services.funnel_service.business_event_service.emit",
        new_callable=AsyncMock,
    ):
        first = await FunnelWebhookHandler().handle_checkout_completed(
            organization_id=org.id,
            checkout_session_id=checkout.id,
            customer_email="fixture@example.invalid",
            stripe_session_id="cs_sim_idempotent",
            db=db_session,
        )
        second = await FunnelWebhookHandler().handle_checkout_completed(
            organization_id=org.id,
            checkout_session_id=checkout.id,
            customer_email="fixture@example.invalid",
            stripe_session_id="cs_sim_idempotent",
            db=db_session,
        )

    assert first["duplicate"] is False
    assert second == {"order_id": first["order_id"], "duplicate": True}
    mock_send.assert_awaited_once()
    assert await db_session.scalar(
        select(func.count()).select_from(FunnelOrder).where(
            FunnelOrder.checkout_session_id == checkout.id
        )
    ) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(FunnelOrderItem).where(
            FunnelOrderItem.organization_id == org.id
        )
    ) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(DeliveryAccess).where(
            DeliveryAccess.organization_id == org.id
        )
    ) == 1


@pytest.mark.asyncio
async def test_synthetic_simulation_accepts_only_both_null_stripe_ids(
    db_session: AsyncSession, enable_test_checkout_simulation,
):
    from app.services.funnel_service import FunnelWebhookHandler

    org = await OrganizationFactory.build(db_session)
    product = DigitalProduct(
        id=uuid4(),
        organization_id=org.id,
        name="P",
        slug="p-synthetic-sim",
        price_amount=Decimal("0.00"),
        currency="THB",
        status="published",
    )
    checkout = FunnelCheckoutSession(
        id=uuid4(),
        organization_id=org.id,
        product_id=product.id,
        stripe_session_id=None,
        status="pending",
        amount=Decimal("0.00"),
        currency="THB",
    )
    db_session.add_all([product, checkout])
    await db_session.commit()

    with patch(
        "app.services.funnel_service.mock_email_provider.send_delivery_email",
        new_callable=AsyncMock,
    ), patch(
        "app.services.funnel_service.business_event_service.emit",
        new_callable=AsyncMock,
    ):
        result = await FunnelWebhookHandler().handle_checkout_completed(
            organization_id=org.id,
            checkout_session_id=checkout.id,
            customer_email="fixture@example.invalid",
            stripe_session_id=None,
            db=db_session,
        )

    assert result["duplicate"] is False


@pytest.mark.asyncio
async def test_simulation_rejects_query_tenant_override(
    async_client,
):
    response = await async_client.post(
        "/api/v1/funnel/webhook/checkout-completed",
        params={
            "checkout_session_id": str(uuid4()),
            "customer_email": "fixture@example.invalid",
            "organization_id": str(UUID(int=0)),
        },
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_simulation_is_denied_in_production_even_if_testing_flag_is_true(
    db_session: AsyncSession, monkeypatch,
):
    from app.api.funnel import simulate_checkout_webhook
    from app.auth.context import AuthContext
    from app.services.funnel_service import FunnelWebhookHandler

    monkeypatch.setattr(settings, "TESTING", True)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    organization_id = uuid4()

    with pytest.raises(HTTPException) as route_error:
        await simulate_checkout_webhook(
            checkout_session_id=uuid4(),
            customer_email="fixture@example.invalid",
            stripe_session_id="cs_caller_supplied",
            auth=AuthContext(organization_id=organization_id),
            db=db_session,
        )
    assert route_error.value.status_code == 404

    with pytest.raises(ValueError, match="only available in test configuration"):
        await FunnelWebhookHandler().handle_checkout_completed(
            organization_id=organization_id,
            checkout_session_id=uuid4(),
            customer_email="fixture@example.invalid",
            stripe_session_id=None,
        )


@pytest.mark.asyncio
async def test_simulation_route_accepts_explicit_test_configuration(
    db_session: AsyncSession, enable_test_checkout_simulation,
):
    from app.api.funnel import simulate_checkout_webhook
    from app.auth.context import AuthContext
    from app.models.funnel import FunnelOrder

    org = await OrganizationFactory.build(db_session)
    product = DigitalProduct(
        id=uuid4(), organization_id=org.id, name="Test-only P",
        slug="p-test-only-simulation", price_amount=Decimal("0.00"),
        currency="THB", status="published",
    )
    checkout = FunnelCheckoutSession(
        id=uuid4(), organization_id=org.id, product_id=product.id,
        stripe_session_id=None, status="pending", amount=Decimal("0.00"),
        currency="THB",
    )
    db_session.add_all([product, checkout])
    await db_session.commit()

    with patch(
        "app.services.funnel_service.mock_email_provider.send_delivery_email",
        new_callable=AsyncMock,
    ) as mock_send, patch(
        "app.services.funnel_service.business_event_service.emit",
        new_callable=AsyncMock,
    ), patch(
        "app.services.email_service.EmailService.send_email",
        new_callable=AsyncMock,
    ) as provider_send:
        result = await simulate_checkout_webhook(
            checkout_session_id=checkout.id,
            customer_email="fixture@example.invalid",
            stripe_session_id=None,
            auth=AuthContext(organization_id=org.id),
            db=db_session,
        )

    assert result["duplicate"] is False
    order = await db_session.scalar(
        select(FunnelOrder).where(FunnelOrder.checkout_session_id == checkout.id)
    )
    assert order is not None and order.status == "paid"
    mock_send.assert_awaited_once()
    provider_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_analytics_failure_does_not_abort_fulfillment_or_duplicate_replay(
    db_session: AsyncSession, monkeypatch, caplog,
):
    from app.services.funnel_delivery_email_service import DeliveryEmailOutcome
    from app.services.funnel_order_service import FunnelOrderService

    org = await OrganizationFactory.build(db_session)
    product = DigitalProduct(
        id=uuid4(), organization_id=org.id, name="Analytics retry P",
        slug="p-analytics-retry", price_amount=Decimal("20.00"),
        currency="THB", status="published",
    )
    asset = DeliveryAsset(
        id=uuid4(), organization_id=org.id, product_id=product.id,
        title="Analytics retry asset", asset_type="text", content_body="fixture",
        is_active=True,
    )
    checkout = FunnelCheckoutSession(
        id=uuid4(), organization_id=org.id, product_id=product.id,
        stripe_session_id="cs_analytics_failure", status="pending",
        amount=Decimal("20.00"), currency="THB",
        customer_email="fixture@example.invalid",
    )
    db_session.add_all([product, asset, checkout])
    await db_session.commit()
    event = {
        "id": "cs_analytics_failure",
        "customer_details": {"email": "fixture@example.invalid"},
        "metadata": {
            "organization_id": str(org.id),
            "product_id": str(product.id),
            "funnel_checkout_session_id": str(checkout.id),
        },
    }
    monkeypatch.setattr(settings, "CELERY_BROKER_URL", "")
    monkeypatch.setattr(settings, "REDIS_URL", "")

    with patch(
        "app.services.funnel_analytics_service.FunnelAnalyticsService.log_event",
        new_callable=AsyncMock,
        side_effect=RuntimeError("analytics unavailable"),
    ) as log_event, patch(
        "app.services.funnel_delivery_email_service.FunnelDeliveryEmailService.send_delivery_links",
        new_callable=AsyncMock,
        return_value=DeliveryEmailOutcome("suppressed"),
    ) as send_delivery, patch(
        "app.services.email_service.EmailService.send_email",
        new_callable=AsyncMock,
    ) as provider_send, patch(
        "app.services.automation_email_service.AutomationEmailService.trigger_post_purchase",
        new_callable=AsyncMock,
    ):
        first = await FunnelOrderService(db_session).create_order_from_checkout_completed(event)
        replay = await FunnelOrderService(db_session).create_order_from_checkout_completed(event)

    assert first is not None and replay is not None and replay.id == first.id
    assert log_event.await_count == 1
    assert "Purchase analytics unavailable after checkout commit" in caplog.text
    send_delivery.assert_awaited_once()
    provider_send.assert_not_awaited()
    assert await db_session.scalar(
        select(func.count()).select_from(FunnelOrder).where(
            FunnelOrder.checkout_session_id == checkout.id
        )
    ) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(FunnelOrderItem).where(
            FunnelOrderItem.order_id == first.id
        )
    ) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(DeliveryAccess).where(
            DeliveryAccess.order_id == first.id
        )
    ) == 1


@pytest.mark.asyncio
async def test_simulation_delivery_asset_grant_checks_product_and_org_ownership(
    db_session: AsyncSession,
):
    from app.services.funnel_service import DeliveryAccessService

    org = await OrganizationFactory.build(db_session)
    other_org = await OrganizationFactory.build(db_session)
    organization_id = org.id
    product = DigitalProduct(
        id=uuid4(),
        organization_id=org.id,
        name="P",
        slug="p-access-asset-owner",
        price_amount=Decimal("10.00"),
        currency="THB",
        status="published",
    )
    other_product = DigitalProduct(
        id=uuid4(),
        organization_id=org.id,
        name="Other P",
        slug="p-access-asset-other-product",
        price_amount=Decimal("10.00"),
        currency="THB",
        status="published",
    )
    foreign_product = DigitalProduct(
        id=uuid4(),
        organization_id=other_org.id,
        name="Foreign P",
        slug="p-access-asset-foreign-org",
        price_amount=Decimal("10.00"),
        currency="THB",
        status="published",
    )
    order = FunnelOrder(
        id=uuid4(),
        organization_id=org.id,
        status="paid",
        subtotal_amount=Decimal("10.00"),
        total_amount=Decimal("10.00"),
        currency="THB",
    )
    owned_asset = DeliveryAsset(
        id=uuid4(),
        organization_id=org.id,
        product_id=product.id,
        asset_type="file",
        title="Owned asset",
        is_active=True,
    )
    wrong_product_asset = DeliveryAsset(
        id=uuid4(),
        organization_id=org.id,
        product_id=other_product.id,
        asset_type="file",
        title="Other product asset",
        is_active=True,
    )
    foreign_asset = DeliveryAsset(
        id=uuid4(),
        organization_id=other_org.id,
        product_id=foreign_product.id,
        asset_type="file",
        title="Foreign asset",
        is_active=True,
    )
    db_session.add_all(
        [
            product,
            other_product,
            foreign_product,
            order,
            owned_asset,
            wrong_product_asset,
            foreign_asset,
        ]
    )
    await db_session.commit()
    owned_asset_id = owned_asset.id

    access, token = await DeliveryAccessService().grant_access(
        organization_id=org.id,
        order_id=order.id,
        product_id=product.id,
        delivery_asset_id=owned_asset_id,
        db=db_session,
    )
    assert access.delivery_asset_id == owned_asset_id
    assert token

    with pytest.raises(ValueError, match="delivery_asset_not_owned_by_product"):
        await DeliveryAccessService().grant_access(
            organization_id=org.id,
            order_id=order.id,
            product_id=product.id,
            delivery_asset_id=wrong_product_asset.id,
            db=db_session,
        )
    with pytest.raises(ValueError, match="delivery_asset_not_owned_by_product"):
        await DeliveryAccessService().grant_access(
            organization_id=org.id,
            order_id=order.id,
            product_id=product.id,
            delivery_asset_id=foreign_asset.id,
            db=db_session,
        )

    await db_session.rollback()
    assert await db_session.scalar(
        select(func.count()).select_from(DeliveryAccess).where(
            DeliveryAccess.organization_id == organization_id,
            DeliveryAccess.delivery_asset_id == owned_asset_id,
        )
    ) == 1


@pytest.mark.asyncio
async def test_public_open_reads_both_delivery_asset_columns(
    db_session: AsyncSession,
):
    from types import SimpleNamespace
    from app.api import funnel as funnel_api

    org = await OrganizationFactory.build(db_session)
    product = DigitalProduct(
        id=uuid4(),
        organization_id=org.id,
        name="P",
        slug="p-public-open-asset",
        price_amount=Decimal("10.00"),
        currency="THB",
        status="published",
    )
    asset = DeliveryAsset(
        id=uuid4(),
        organization_id=org.id,
        product_id=product.id,
        asset_type="file",
        title="Public asset title",
        is_active=True,
    )
    order = FunnelOrder(
        id=uuid4(),
        organization_id=org.id,
        status="paid",
        subtotal_amount=Decimal("10.00"),
        total_amount=Decimal("10.00"),
        currency="THB",
    )
    db_session.add_all([product, asset, order])
    await db_session.commit()

    for column in ("delivery_asset_id", "asset_id"):
        access = SimpleNamespace(
            id=uuid4(),
            organization_id=org.id,
            order_id=order.id,
            product_id=product.id,
            delivery_asset_id=asset.id if column == "delivery_asset_id" else None,
            asset_id=asset.id if column == "asset_id" else None,
            status="active",
            first_opened_at=None,
        )
        with patch(
            "app.api.funnel.delivery_access_service.verify_access",
            new=AsyncMock(return_value=access),
        ), patch(
            "app.api.funnel.delivery_access_service.record_open",
            new=AsyncMock(return_value=access),
        ):
            response = await funnel_api.open_delivery("fixture-token", db=db_session)
        assert response.asset_title == "Public asset title"
