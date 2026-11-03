import pytest
import json
from uuid import uuid4
from decimal import Decimal
from unittest.mock import MagicMock, patch

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import DigitalProduct, FunnelCheckoutSession, FunnelOrder, FunnelOrderItem, DeliveryAccess
from app.models.organization import Organization
from tests.factories import OrganizationFactory

@pytest.fixture
def mock_email_service():
    with patch("app.services.email_service.send_email") as mock:
        yield mock

@pytest.fixture
def mock_webhook_signature():
    with patch("stripe.Webhook.construct_event") as mock:
        yield mock

@pytest.mark.asyncio
class TestFunnelWebhookOrder:
    """Test the digital product funnel webhook and order creation"""

    async def test_webhook_creates_order_and_item(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature
    ):
        """1. checkout.session.completed creates FunnelOrder and FunnelOrderItem"""
        org = await OrganizationFactory.build(db_session)
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="Webhook Prod", slug="webhook-prod", 
            price_amount=Decimal("150.00"), currency="THB", status="published"
        )
        db_session.add(prod)
        
        checkout = FunnelCheckoutSession(
            id=uuid4(), organization_id=org.id, product_id=prod.id, 
            status="pending", amount=prod.price_amount, currency=prod.currency
        )
        db_session.add(checkout)
        await db_session.commit()

        stripe_session_id = "cs_webhook_123"
        payment_intent_id = "pi_webhook_123"
        
        # Prepare fake Stripe event
        event_data = {
            "id": stripe_session_id,
            "payment_intent": payment_intent_id,
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

        response = await async_client.post(
            "/api/v1/funnel/webhooks/stripe",
            headers={"stripe-signature": "fake_sig"},
            content=json.dumps({"id": "evt_123"})
        )
        
        assert response.status_code == 200
        assert response.json()["received"] is True
        
        # Verify order creation
        stmt = select(FunnelOrder).where(FunnelOrder.checkout_session_id == checkout.id)
        res = await db_session.execute(stmt)
        order = res.scalar_one()
        assert order.status == "paid"
        assert order.total_amount == Decimal("150.00")
        assert order.customer_email == "buyer@test.com"
        assert order.stripe_session_id == stripe_session_id
        assert order.stripe_payment_intent_id == payment_intent_id

        # Verify order item
        stmt = select(FunnelOrderItem).where(FunnelOrderItem.order_id == order.id)
        res = await db_session.execute(stmt)
        item = res.scalar_one()
        assert item.product_id == prod.id
        assert item.unit_amount == Decimal("150.00")

        # Verify checkout session update
        await db_session.refresh(checkout)
        assert checkout.status == "completed"
        assert checkout.completed_at is not None

    async def test_webhook_idempotency(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature
    ):
        """8. Duplicate webhook does not create duplicate order"""
        org = await OrganizationFactory.build(db_session)
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="P", slug="p", 
            price_amount=Decimal("100.00"), currency="THB", status="published"
        )
        db_session.add(prod)
        checkout = FunnelCheckoutSession(
            id=uuid4(), organization_id=org.id, product_id=prod.id, 
            status="pending", amount=Decimal("100.00"), currency="THB"
        )
        db_session.add(checkout)
        await db_session.commit()

        event_data = {
            "id": "cs_dup_123",
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

        # First call
        await async_client.post("/api/v1/funnel/webhooks/stripe", headers={"stripe-signature": "f"}, content="{}")
        
        # Second call
        response = await async_client.post("/api/v1/funnel/webhooks/stripe", headers={"stripe-signature": "f"}, content="{}")
        assert response.status_code == 200
        
        # Count orders
        stmt = select(FunnelOrder).where(FunnelOrder.stripe_session_id == "cs_dup_123")
        res = await db_session.execute(stmt)
        orders = res.scalars().all()
        assert len(orders) == 1

    async def test_invalid_signature_returns_400(
        self, async_client: AsyncClient, mock_webhook_signature
    ):
        """12. Invalid signature returns 400"""
        import stripe
        mock_webhook_signature.side_effect = stripe.error.SignatureVerificationError("Invalid", "sig")
        
        response = await async_client.post(
            "/api/v1/funnel/webhooks/stripe",
            headers={"stripe-signature": "bad"},
            content="{}"
        )
        assert response.status_code == 400

    async def test_missing_metadata_no_order(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature
    ):
        """9. Missing metadata returns safe error / no order"""
        mock_webhook_signature.return_value = {
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_missing", "metadata": {}}}
        }
        
        response = await async_client.post("/api/v1/funnel/webhooks/stripe", headers={"stripe-signature": "f"}, content="{}")
        assert response.status_code == 200 # Webhook acknowledged
        assert response.json()["order_id"] is None
        
        stmt = select(FunnelOrder).where(FunnelOrder.stripe_session_id == "cs_missing")
        res = await db_session.execute(stmt)
        assert res.scalar_one_or_none() is None

    async def test_cross_org_metadata_mismatch_no_order(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature
    ):
        """10. Cross-org metadata mismatch does not create order"""
        org1 = await OrganizationFactory.build(db_session)
        org2 = await OrganizationFactory.build(db_session)
        prod = DigitalProduct(
            id=uuid4(), organization_id=org1.id, name="P", slug="p1", 
            price_amount=Decimal("100.00"), currency="THB", status="published"
        )
        checkout = FunnelCheckoutSession(
            id=uuid4(), organization_id=org1.id, product_id=prod.id, 
            status="pending", amount=Decimal("100.00"), currency="THB"
        )
        db_session.add_all([prod, checkout])
        await db_session.commit()

        # Metadata claims org2, but checkout session belongs to org1
        event_data = {
            "id": "cs_mismatch",
            "metadata": {
                "organization_id": str(org2.id),
                "product_id": str(prod.id),
                "funnel_checkout_session_id": str(checkout.id)
            }
        }
        mock_webhook_signature.return_value = {"type": "checkout.session.completed", "data": {"object": event_data}}

        response = await async_client.post("/api/v1/funnel/webhooks/stripe", headers={"stripe-signature": "f"}, content="{}")
        assert response.status_code == 200
        
        stmt = select(FunnelOrder).where(FunnelOrder.stripe_session_id == "cs_mismatch")
        res = await db_session.execute(stmt)
        assert res.scalar_one_or_none() is None

    async def test_unsupported_event_acknowledged(
        self, async_client: AsyncClient, mock_webhook_signature
    ):
        """11. Unsupported event type returns acknowledged response"""
        mock_webhook_signature.return_value = {"type": "payment_intent.succeeded", "data": {"object": {}}}
        
        response = await async_client.post("/api/v1/funnel/webhooks/stripe", headers={"stripe-signature": "f"}, content="{}")
        assert response.status_code == 200
        assert response.json()["received"] is True
        assert response.json()["event_type"] == "payment_intent.succeeded"

    async def test_webhook_no_premature_delivery_access(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature
    ):
        """13. Webhook does not grant DeliveryAccess yet"""
        org = await OrganizationFactory.build(db_session)
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="P", slug="p2", 
            price_amount=Decimal("100.00"), currency="THB", status="published"
        )
        checkout = FunnelCheckoutSession(
            id=uuid4(), organization_id=org.id, product_id=prod.id, 
            status="pending", amount=Decimal("100.00"), currency="THB"
        )
        db_session.add_all([prod, checkout])
        await db_session.commit()

        event_data = {
            "id": "cs_no_delivery",
            "metadata": {
                "organization_id": str(org.id),
                "product_id": str(prod.id),
                "funnel_checkout_session_id": str(checkout.id)
            }
        }
        mock_webhook_signature.return_value = {"type": "checkout.session.completed", "data": {"object": event_data}}

        await async_client.post("/api/v1/funnel/webhooks/stripe", headers={"stripe-signature": "f"}, content="{}")
        
        # Verify no delivery access records created
        stmt = select(DeliveryAccess).where(DeliveryAccess.organization_id == org.id)
        res = await db_session.execute(stmt)
        assert len(res.scalars().all()) == 0

    async def test_webhook_no_premature_delivery_email(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature, mock_email_service
    ):
        """14. Webhook does not send delivery email yet"""
        org = await OrganizationFactory.build(db_session)
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="P", slug="p3", 
            price_amount=Decimal("100.00"), currency="THB", status="published"
        )
        checkout = FunnelCheckoutSession(
            id=uuid4(), organization_id=org.id, product_id=prod.id, 
            status="pending", amount=Decimal("100.00"), currency="THB"
        )
        db_session.add_all([prod, checkout])
        await db_session.commit()

        event_data = {
            "id": "cs_no_email",
            "metadata": {
                "organization_id": str(org.id),
                "product_id": str(prod.id),
                "funnel_checkout_session_id": str(checkout.id)
            }
        }
        mock_webhook_signature.return_value = {"type": "checkout.session.completed", "data": {"object": event_data}}

        await async_client.post("/api/v1/funnel/webhooks/stripe", headers={"stripe-signature": "f"}, content="{}")
        
        # Verify email service was not called
        assert mock_email_service.called is False


