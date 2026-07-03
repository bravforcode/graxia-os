import pytest
from uuid import uuid4
from decimal import Decimal
from unittest.mock import patch, AsyncMock

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import DigitalProduct, FunnelCheckoutSession, FunnelOrder, DeliveryAccess, DeliveryAsset
from tests.factories import OrganizationFactory

@pytest.fixture
def mock_webhook_signature():
    with patch("stripe.Webhook.construct_event") as mock:
        yield mock

@pytest.mark.asyncio
class TestFunnelWebhookDelivery:
    """Test that webhooks correctly trigger delivery access grants"""

    async def test_webhook_creates_order_and_delivery_access(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature
    ):
        """1. Webhook creates order and delivery access"""
        org = await OrganizationFactory.build(db_session)
        
        # 1. Setup Product with an active Asset
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="Test Prod", slug="p-web-del",
            price_amount=Decimal("100.00"), currency="THB", status="published"
        )
        asset = DeliveryAsset(
            id=uuid4(), organization_id=org.id, product_id=prod.id,
            title="Webhook Asset", asset_type="text", content_body="Success!", is_active=True
        )
        
        # 2. Setup existing local Checkout Session
        checkout = FunnelCheckoutSession(
            id=uuid4(), organization_id=org.id, product_id=prod.id, 
            status="pending", amount=Decimal("100.00"), currency="THB"
        )
        db_session.add_all([prod, asset, checkout])
        await db_session.commit()

        # 3. Simulate Stripe Webhook
        event_data = {
            "id": "cs_webhook_delivery",
            "payment_intent": "pi_123",
            "customer_details": {"email": "buyer@test.com"},
            "metadata": {
                "organization_id": str(org.id),
                "product_id": str(prod.id),
                "funnel_checkout_session_id": str(checkout.id)
            }
        }
        mock_webhook_signature.return_value = {
            "type": "checkout.session.completed", 
            "data": {"object": event_data}
        }

        # 4. Trigger Webhook
        response = await async_client.post(
            "/api/v1/funnel/webhooks/stripe", 
            headers={"stripe-signature": "valid"}, 
            content="{}"
        )
        assert response.status_code == 200
        
        # 5. Verify Order created
        stmt = select(FunnelOrder).where(FunnelOrder.stripe_session_id == "cs_webhook_delivery")
        res = await db_session.execute(stmt)
        order = res.scalar_one()
        assert order.status == "paid"

        # 6. Verify Delivery Access created
        stmt = select(DeliveryAccess).where(DeliveryAccess.order_id == order.id)
        res = await db_session.execute(stmt)
        accesses = res.scalars().all()
        assert len(accesses) == 1
        assert accesses[0].asset_id == asset.id
        assert accesses[0].access_token_hash is not None

    async def test_duplicate_webhook_is_idempotent_for_delivery(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature
    ):
        """2. Duplicate webhook remains idempotent (does not duplicate delivery access)"""
        org = await OrganizationFactory.build(db_session)
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="P", slug="p-dup",
            price_amount=Decimal("1"), status="published"
        )
        asset = DeliveryAsset(
            id=uuid4(), organization_id=org.id, product_id=prod.id,
            title="A", asset_type="text", is_active=True
        )
        checkout = FunnelCheckoutSession(
            id=uuid4(), organization_id=org.id, product_id=prod.id, 
            status="pending", amount=Decimal("1"), currency="THB"
        )
        db_session.add_all([prod, asset, checkout])
        await db_session.commit()

        event_data = {
            "id": "cs_idempotent",
            "metadata": {
                "organization_id": str(org.id),
                "product_id": str(prod.id),
                "funnel_checkout_session_id": str(checkout.id)
            }
        }
        mock_webhook_signature.return_value = {"type": "checkout.session.completed", "data": {"object": event_data}}

        # First call
        await async_client.post("/api/v1/funnel/webhooks/stripe", headers={"stripe-signature": "f"}, content="{}")
        
        # Second call
        await async_client.post("/api/v1/funnel/webhooks/stripe", headers={"stripe-signature": "f"}, content="{}")
        
        # Verify only 1 order and 1 delivery access
        stmt = select(FunnelOrder).where(FunnelOrder.stripe_session_id == "cs_idempotent")
        order_res = await db_session.execute(stmt)
        orders = order_res.scalars().all()
        assert len(orders) == 1
        
        stmt = select(DeliveryAccess).where(DeliveryAccess.order_id == orders[0].id)
        access_res = await db_session.execute(stmt)
        assert len(access_res.scalars().all()) == 1

    async def test_expired_session_sends_abandoned_cart_and_sets_dedup_flag(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature
    ):
        """3. checkout.session.expired fires abandoned cart email and sets dedup flag"""
        org = await OrganizationFactory.build(db_session)
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="Test Prod", slug="p-exp-aban",
            price_amount=Decimal("200.00"), currency="THB", status="published"
        )
        checkout = FunnelCheckoutSession(
            id=uuid4(), organization_id=org.id, product_id=prod.id,
            status="pending", amount=Decimal("200.00"), currency="THB",
            customer_email="cart@abandon.com"
        )
        db_session.add_all([prod, checkout])
        await db_session.commit()

        event_data = {
            "metadata": {
                "organization_id": str(org.id),
                "product_id": str(prod.id),
                "funnel_checkout_session_id": str(checkout.id)
            }
        }
        mock_webhook_signature.return_value = {
            "type": "checkout.session.expired",
            "data": {"object": event_data}
        }

        with patch("app.services.automation_email_service.email_service.send_email", new_callable=AsyncMock) as mock_send:
            response = await async_client.post(
                "/api/v1/funnel/webhooks/stripe",
                headers={"stripe-signature": "valid"},
                content="{}"
            )
            assert response.status_code == 200
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args
            assert call_kwargs.kwargs["to"] == "cart@abandon.com"
            assert call_kwargs.kwargs["template_name"] == "funnel_automation_abandoned_cart"

        # Verify dedup flag was set
        stmt = select(FunnelCheckoutSession).where(FunnelCheckoutSession.id == checkout.id)
        res = await db_session.execute(stmt)
        session = res.scalar_one()
        assert session.abandoned_email_sent_at is not None

    async def test_duplicate_expired_event_is_deduped(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature
    ):
        """4. Second checkout.session.expired for same session is a no-op"""
        org = await OrganizationFactory.build(db_session)
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="P", slug="p-exp-dedup",
            price_amount=Decimal("1"), status="published"
        )
        checkout = FunnelCheckoutSession(
            id=uuid4(), organization_id=org.id, product_id=prod.id,
            status="pending", amount=Decimal("1"), currency="THB",
            customer_email="dup@test.com"
        )
        db_session.add_all([prod, checkout])
        await db_session.commit()

        event_data = {
            "metadata": {
                "organization_id": str(org.id),
                "product_id": str(prod.id),
                "funnel_checkout_session_id": str(checkout.id)
            }
        }
        mock_webhook_signature.return_value = {
            "type": "checkout.session.expired",
            "data": {"object": event_data}
        }

        # First call — should send email
        with patch("app.services.automation_email_service.email_service.send_email", new_callable=AsyncMock) as mock_send:
            await async_client.post(
                "/api/v1/funnel/webhooks/stripe",
                headers={"stripe-signature": "valid"}, content="{}"
            )
            assert mock_send.call_count == 1

        # Second call — dedup flag set, should NOT send email
        with patch("app.services.automation_email_service.email_service.send_email", new_callable=AsyncMock) as mock_send:
            await async_client.post(
                "/api/v1/funnel/webhooks/stripe",
                headers={"stripe-signature": "valid"}, content="{}"
            )
            mock_send.assert_not_called()
