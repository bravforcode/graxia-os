import pytest
from uuid import uuid4
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from app.models.funnel import DigitalProduct, FunnelCheckoutSession, FunnelOrder, DeliveryAccess, DeliveryAsset
from app.services.funnel_delivery_email_service import FunnelDeliveryEmailService
from tests.factories import OrganizationFactory

@pytest.fixture(autouse=True)
def clean_sent_emails():
    # Clear in-memory mock sent emails before/after each test
    FunnelDeliveryEmailService.sent_emails.clear()
    yield
    FunnelDeliveryEmailService.sent_emails.clear()

@pytest.fixture
def mock_webhook_signature():
    with patch("stripe.Webhook.construct_event") as mock:
        yield mock

@pytest.mark.asyncio
class TestFunnelDeliveryEmail:
    """Test Suite for customer purchase email notification subsystem"""

    async def test_email_service_structures_links_and_names(self, db_session: AsyncSession):
        """1. Verify email service structures correct download links and product names"""
        org = await OrganizationFactory.build(db_session)
        
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="Awesome Book", slug="awesome-book",
            price_amount=Decimal("19.99"), status="published"
        )
        asset = DeliveryAsset(
            id=uuid4(), organization_id=org.id, product_id=prod.id,
            title="Book PDF", asset_type="text", is_active=True
        )
        order = FunnelOrder(
            id=uuid4(), organization_id=org.id, status="paid",
            subtotal_amount=Decimal("19.99"), total_amount=Decimal("19.99"), currency="USD",
            customer_email="customer@example.com"
        )
        db_session.add_all([prod, asset, order])
        await db_session.commit()

        access = DeliveryAccess(
            id=uuid4(), organization_id=org.id, order_id=order.id, product_id=prod.id,
            asset_id=asset.id, access_token_hash="dummyhash", status="active", download_count=0
        )
        db_session.add(access)
        await db_session.commit()

        email_service = FunnelDeliveryEmailService(db_session)
        success = await email_service.send_delivery_links(
            organization_id=org.id,
            order_id=order.id,
            customer_email="customer@example.com",
            delivery_accesses=[(access, "secret_token_123")]
        )
        assert success is True
        
        # Verify in-memory tracking
        assert len(FunnelDeliveryEmailService.sent_emails) == 1
        sent = FunnelDeliveryEmailService.sent_emails[0]
        assert sent["to"] == "customer@example.com"
        assert sent["template_name"] == "funnel_delivery"
        assert sent["idempotency_key"] == f"funnel_delivery:{order.id}"
        
        # Verify item info inside template data
        items = sent["template_data"]["delivery_items"]
        assert len(items) == 1
        assert items[0]["product_name"] == "Awesome Book"
        assert "secret_token_123" in items[0]["download_url"]

    async def test_webhook_triggers_email_delivery(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature
    ):
        """2. Verify that completing webhook automatically triggers emailing delivery links"""
        org = await OrganizationFactory.build(db_session)
        
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="Membership Premium", slug="prem",
            price_amount=Decimal("50.00"), currency="USD", status="published"
        )
        asset = DeliveryAsset(
            id=uuid4(), organization_id=org.id, product_id=prod.id,
            title="Asset A", asset_type="text", content_body="Exclusive", is_active=True
        )
        checkout = FunnelCheckoutSession(
            id=uuid4(), organization_id=org.id, product_id=prod.id, 
            status="pending", amount=Decimal("50.00"), currency="USD", customer_email="buyer_email@test.com"
        )
        db_session.add_all([prod, asset, checkout])
        await db_session.commit()

        event_data = {
            "id": "cs_webhook_email_test",
            "payment_intent": "pi_email_123",
            "customer_details": {"email": "buyer_email@test.com"},
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

        # Clear sent emails list
        FunnelDeliveryEmailService.sent_emails.clear()

        # Trigger Webhook
        response = await async_client.post(
            "/api/v1/funnel/webhooks/stripe", 
            headers={"stripe-signature": "valid"}, 
            content="{}"
        )
        assert response.status_code == 200

        # Verify email is queued
        assert len(FunnelDeliveryEmailService.sent_emails) == 1
        sent = FunnelDeliveryEmailService.sent_emails[0]
        assert sent["to"] == "buyer_email@test.com"
        assert sent["template_data"]["delivery_items"][0]["product_name"] == "Membership Premium"

    async def test_email_error_handled_gracefully(self, db_session: AsyncSession):
        """3. Verify that email provider errors do not crash order generation flow"""
        org = await OrganizationFactory.build(db_session)
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="Book", slug="bk",
            price_amount=Decimal("1.00"), status="published"
        )
        asset = DeliveryAsset(
            id=uuid4(), organization_id=org.id, product_id=prod.id,
            title="Book PDF", asset_type="text", is_active=True
        )
        order = FunnelOrder(
            id=uuid4(), organization_id=org.id, status="paid",
            subtotal_amount=Decimal("1.00"), total_amount=Decimal("1.00"), currency="USD",
            customer_email="customer@example.com"
        )
        db_session.add_all([prod, asset, order])
        await db_session.commit()

        access = DeliveryAccess(
            id=uuid4(), organization_id=org.id, order_id=order.id, product_id=prod.id,
            asset_id=asset.id, access_token_hash="dummyhash", status="active", download_count=0
        )
        db_session.add(access)
        await db_session.commit()

        email_service = FunnelDeliveryEmailService(db_session)
        
        # Force send_email to raise Exception
        with patch.object(email_service.email_service, "send_email", side_effect=Exception("SMTP Out of Service")):
            success = await email_service.send_delivery_links(
                organization_id=org.id,
                order_id=order.id,
                customer_email="customer@example.com",
                delivery_accesses=[(access, "secret_token_123")]
            )
            # Should fail gracefully and return False instead of raising exception
            assert success is False
