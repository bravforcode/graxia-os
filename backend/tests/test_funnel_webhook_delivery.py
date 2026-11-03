import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import UTC, datetime
from unittest.mock import patch, AsyncMock

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.funnel import (
    ConversionEvent,
    DigitalProduct,
    FunnelCheckoutSession,
    FunnelOrder,
    DeliveryAccess,
    DeliveryAsset,
)
from app.services.automation_email_service import AutomationEmailService
from app.services.funnel_delivery_email_service import DeliveryEmailOutcome
from app.services.funnel_delivery_service import FunnelDeliveryService
from app.services.funnel_order_service import FunnelOrderService
from tests.factories import OrganizationFactory

@pytest.fixture
def mock_webhook_signature():
    with patch("stripe.Webhook.construct_event") as mock:
        yield mock

@pytest.mark.asyncio
class TestFunnelWebhookDelivery:
    """Test that webhooks correctly trigger delivery access grants"""

    @pytest.fixture(autouse=True)
    def mock_all_email_provider_paths(self):
        with patch(
            "app.services.funnel_delivery_email_service.FunnelDeliveryEmailService.send_delivery_links",
            new_callable=AsyncMock,
            return_value=DeliveryEmailOutcome("suppressed"),
        ) as delivery_send, patch(
            "app.services.email_service.EmailService.send_email",
            new_callable=AsyncMock,
            return_value={"id": "test-provider-reference", "status": "sent"},
        ) as provider_send:
            self.delivery_send_mock = delivery_send
            self.provider_send_mock = provider_send
            yield

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
            status="pending", amount=Decimal("100.00"), currency="THB",
            stripe_session_id="cs_webhook_delivery",
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
        self.delivery_send_mock.assert_awaited_once()
        delivery_call = self.delivery_send_mock.await_args.kwargs
        assert delivery_call["organization_id"] == org.id
        assert delivery_call["order_id"] == order.id
        assert delivery_call["customer_email"] == "buyer@test.com"
        assert len(delivery_call["delivery_accesses"]) == 1
        self.provider_send_mock.assert_not_awaited()

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
            status="pending", amount=Decimal("1"), currency="THB",
            stripe_session_id="cs_idempotent",
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
        self.delivery_send_mock.assert_awaited_once()
        self.provider_send_mock.assert_not_awaited()

    async def test_expired_session_sends_abandoned_cart_and_sets_dedup_flag(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature
    ):
        """3. checkout.session.expired fires abandoned cart email and sets dedup flag"""
        org = await OrganizationFactory.build(db_session)
        contact = Contact(
            id=uuid4(),
            organization_id=org.id,
            name="Consenting cart customer",
            email="cart@abandon.com",
            contact_type="lead",
            marketing_consent=True,
            marketing_consent_at=datetime.now(UTC),
            consent_version="test-v1",
        )
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="Test Prod", slug="p-exp-aban",
            price_amount=Decimal("200.00"), currency="THB", status="published"
        )
        stripe_expires_at = int(datetime.now(UTC).timestamp()) - 30
        stripe_session_id = "cs_expired_cart"
        checkout = FunnelCheckoutSession(
            id=uuid4(), organization_id=org.id, product_id=prod.id,
            status="pending", amount=Decimal("200.00"), currency="THB",
            customer_email="cart@abandon.com", contact_id=contact.id,
            stripe_session_id=stripe_session_id,
            expires_at=datetime.fromtimestamp(stripe_expires_at, tz=UTC),
        )
        db_session.add_all([prod, contact, checkout])
        await db_session.commit()

        event_data = {
            "id": stripe_session_id,
            "expires_at": stripe_expires_at,
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
            mock_send.return_value = {"id": "test-provider-reference", "status": "sent"}
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
        self.delivery_send_mock.assert_not_awaited()

        # Verify dedup flag was set
        stmt = select(FunnelCheckoutSession).where(FunnelCheckoutSession.id == checkout.id)
        res = await db_session.execute(stmt)
        session = res.scalar_one()
        await db_session.refresh(session)
        assert session.abandoned_email_sent_at is not None
        assert session.status == "expired"

    async def test_duplicate_expired_event_is_deduped(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature
    ):
        """4. Second checkout.session.expired for same session is a no-op"""
        org = await OrganizationFactory.build(db_session)
        contact = Contact(
            id=uuid4(),
            organization_id=org.id,
            name="Consenting duplicate customer",
            email="dup@test.com",
            contact_type="lead",
            marketing_consent=True,
            marketing_consent_at=datetime.now(UTC),
            consent_version="test-v1",
        )
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="P", slug="p-exp-dedup",
            price_amount=Decimal("1"), status="published"
        )
        stripe_expires_at = int(datetime.now(UTC).timestamp()) - 30
        stripe_session_id = "cs_expired_dedup"
        checkout = FunnelCheckoutSession(
            id=uuid4(), organization_id=org.id, product_id=prod.id,
            status="pending", amount=Decimal("1"), currency="THB",
            customer_email="dup@test.com", contact_id=contact.id,
            stripe_session_id=stripe_session_id,
            expires_at=datetime.fromtimestamp(stripe_expires_at, tz=UTC),
        )
        db_session.add_all([prod, contact, checkout])
        await db_session.commit()

        event_data = {
            "id": stripe_session_id,
            "expires_at": stripe_expires_at,
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
            mock_send.return_value = {"id": "test-provider-reference", "status": "sent"}
            await async_client.post(
                "/api/v1/funnel/webhooks/stripe",
                headers={"stripe-signature": "valid"}, content="{}"
            )
            assert mock_send.call_count == 1

        # Second call — dedup flag set, should NOT send email
        with patch("app.services.automation_email_service.email_service.send_email", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"id": "test-provider-reference", "status": "sent"}
            await async_client.post(
                "/api/v1/funnel/webhooks/stripe",
                headers={"stripe-signature": "valid"}, content="{}"
            )
            mock_send.assert_not_called()
        self.delivery_send_mock.assert_not_awaited()
        self.provider_send_mock.assert_not_awaited()
        await db_session.refresh(checkout)
        assert checkout.status == "expired"
        assert checkout.abandoned_email_sent_at is not None

    async def test_expired_session_without_marketing_consent_does_not_send(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature
    ):
        org = await OrganizationFactory.build(db_session)
        contact = Contact(
            id=uuid4(),
            organization_id=org.id,
            name="Non-consenting cart customer",
            email="no-consent@test.com",
            contact_type="lead",
            marketing_consent=False,
        )
        product = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="No-consent product",
            slug="p-exp-no-consent", price_amount=Decimal("1"), status="published",
        )
        stripe_expires_at = int(datetime.now(UTC).timestamp()) - 30
        stripe_session_id = "cs_expired_no_consent"
        checkout = FunnelCheckoutSession(
            id=uuid4(), organization_id=org.id, product_id=product.id,
            status="pending", amount=Decimal("1"), currency="THB",
            customer_email=contact.email, contact_id=contact.id,
            stripe_session_id=stripe_session_id,
            expires_at=datetime.fromtimestamp(stripe_expires_at, tz=UTC),
        )
        db_session.add_all([contact, product, checkout])
        await db_session.commit()
        mock_webhook_signature.return_value = {
            "type": "checkout.session.expired",
            "data": {
                "object": {
                    "id": stripe_session_id,
                    "expires_at": stripe_expires_at,
                    "metadata": {
                        "organization_id": str(org.id),
                        "product_id": str(product.id),
                        "funnel_checkout_session_id": str(checkout.id),
                    }
                }
            },
        }

        with patch(
            "app.services.automation_email_service.email_service.send_email",
            new_callable=AsyncMock,
        ) as mock_send:
            response = await async_client.post(
                "/api/v1/funnel/webhooks/stripe",
                headers={"stripe-signature": "valid"},
                content="{}",
            )

        assert response.status_code == 200
        assert response.json()["email_status"] == "suppressed"
        mock_send.assert_not_awaited()
        self.provider_send_mock.assert_not_awaited()
        self.delivery_send_mock.assert_not_awaited()
        await db_session.refresh(checkout)
        assert checkout.status == "expired"

    @pytest.mark.parametrize(
        "invalid_case", ["missing_session", "missing_timestamp", "mismatched_timestamp"]
    )
    async def test_expired_event_without_matching_identity_or_timestamp_is_ignored(
        self,
        invalid_case: str,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_webhook_signature,
        caplog,
    ):
        org = await OrganizationFactory.build(db_session)
        product = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="Pending product",
            slug=f"pending-{invalid_case}", price_amount=Decimal("1"), status="published",
        )
        stripe_expires_at = int(datetime.now(UTC).timestamp()) - 30
        stripe_session_id = f"cs_pending_{invalid_case}"
        checkout = FunnelCheckoutSession(
            id=uuid4(), organization_id=org.id, product_id=product.id,
            status="pending", amount=Decimal("1"), currency="THB",
            stripe_session_id=stripe_session_id,
            expires_at=datetime.fromtimestamp(stripe_expires_at, tz=UTC),
        )
        db_session.add_all([product, checkout])
        await db_session.commit()

        event_data = {
            "id": stripe_session_id,
            "expires_at": stripe_expires_at,
            "metadata": {
                "organization_id": str(org.id),
                "product_id": str(product.id),
                "funnel_checkout_session_id": str(checkout.id),
            },
        }
        if invalid_case == "missing_session":
            event_data.pop("id")
        elif invalid_case == "missing_timestamp":
            event_data.pop("expires_at")
        else:
            event_data["expires_at"] += 1
        mock_webhook_signature.return_value = {
            "type": "checkout.session.expired",
            "data": {"object": event_data},
        }

        with patch(
            "app.services.automation_email_service.email_service.send_email",
            new_callable=AsyncMock,
        ) as mock_send:
            response = await async_client.post(
                "/api/v1/funnel/webhooks/stripe",
                headers={"stripe-signature": "valid"},
                content="{}",
            )

        assert response.status_code == 200
        assert response.json()["email_status"] == "suppressed"
        mock_send.assert_not_awaited()
        await db_session.refresh(checkout)
        assert checkout.status == "pending"
        assert "checkout.session.expired" in caplog.text

    async def test_expired_event_never_overwrites_completed_session(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature
    ):
        org = await OrganizationFactory.build(db_session)
        contact = Contact(
            id=uuid4(), organization_id=org.id, name="Completed buyer",
            email="completed@test.com", contact_type="lead", marketing_consent=True,
            marketing_consent_at=datetime.now(UTC), consent_version="test-v1",
        )
        product = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="Completed product",
            slug="completed-before-expiry", price_amount=Decimal("1"), status="published",
        )
        stripe_expires_at = int(datetime.now(UTC).timestamp()) - 30
        stripe_session_id = "cs_completed_before_expiry"
        checkout = FunnelCheckoutSession(
            id=uuid4(), organization_id=org.id, product_id=product.id,
            status="completed", amount=Decimal("1"), currency="THB",
            customer_email=contact.email, contact_id=contact.id,
            stripe_session_id=stripe_session_id,
            expires_at=datetime.fromtimestamp(stripe_expires_at, tz=UTC),
        )
        db_session.add_all([contact, product, checkout])
        await db_session.commit()
        mock_webhook_signature.return_value = {
            "type": "checkout.session.expired",
            "data": {
                "object": {
                    "id": stripe_session_id,
                    "expires_at": stripe_expires_at,
                    "metadata": {
                        "organization_id": str(org.id),
                        "product_id": str(product.id),
                        "funnel_checkout_session_id": str(checkout.id),
                    },
                }
            },
        }

        with patch(
            "app.services.automation_email_service.email_service.send_email",
            new_callable=AsyncMock,
        ) as mock_send:
            response = await async_client.post(
                "/api/v1/funnel/webhooks/stripe",
                headers={"stripe-signature": "valid"},
                content="{}",
            )

        assert response.status_code == 200
        assert response.json()["email_status"] == "suppressed"
        mock_send.assert_not_awaited()
        await db_session.refresh(checkout)
        assert checkout.status == "completed"


    async def test_marketing_allowed_requires_matching_contact_email(
        self, db_session: AsyncSession
    ):
        org = await OrganizationFactory.build(db_session)
        contact = Contact(
            id=uuid4(), organization_id=org.id, name="Consented Contact",
            email="consented@example.com", contact_type="lead", relationship_strength=1,
            marketing_consent=True, marketing_unsubscribed=False,
            marketing_consent_at=datetime.now(UTC), consent_version="funnel-test-v1",
        )
        db_session.add(contact)
        await db_session.commit()

        service = AutomationEmailService(db_session)
        assert not await service._marketing_allowed(
            org.id, "other-recipient@example.com", contact.id
        )
        assert await service._marketing_allowed(
            org.id, " CONSENTED@example.com ", contact.id
        )

    async def test_marketing_allowed_denies_negative_or_unsubscribed_consent(
        self, db_session: AsyncSession
    ):
        org = await OrganizationFactory.build(db_session)
        denied = [
            Contact(
                id=uuid4(), organization_id=org.id, name="No Consent",
                email="no-consent@example.com", contact_type="lead", relationship_strength=1,
                marketing_consent=False, marketing_unsubscribed=False,
            ),
            Contact(
                id=uuid4(), organization_id=org.id, name="Unsubscribed",
                email="unsubscribed@example.com", contact_type="lead", relationship_strength=1,
                marketing_consent=True, marketing_unsubscribed=True,
                marketing_consent_at=datetime.now(UTC), consent_version="funnel-test-v1",
            ),
        ]
        db_session.add_all(denied)
        await db_session.commit()

        service = AutomationEmailService(db_session)
        for contact in denied:
            assert not await service._marketing_allowed(org.id, contact.email, contact.id)

    @pytest.mark.parametrize("missing", ["marketing_consent_at", "consent_version"])
    async def test_marketing_consent_requires_audit_fields(
        self, db_session: AsyncSession, missing: str
    ):
        org = await OrganizationFactory.build(db_session)
        contact = Contact(
            id=uuid4(), organization_id=org.id, name="Invalid Consent",
            email=f"invalid-{missing}@example.com", contact_type="lead", relationship_strength=1,
            marketing_consent=True, marketing_unsubscribed=False,
            marketing_consent_at=None if missing == "marketing_consent_at" else datetime.now(UTC),
            consent_version=None if missing == "consent_version" else "funnel-test-v1",
        )
        db_session.add(contact)
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_paid_order_rolls_back_when_delivery_fails(
        self, db_session: AsyncSession
    ):
        org = await OrganizationFactory.build(db_session)
        product = DigitalProduct(
            id=uuid4(),
            organization_id=org.id,
            name="Atomic Paid Product",
            slug="atomic-paid-product",
            price_amount=Decimal("100.00"),
            currency="THB",
            status="published",
        )
        checkout = FunnelCheckoutSession(
            id=uuid4(),
            organization_id=org.id,
            product_id=product.id,
            status="pending",
            amount=Decimal("100.00"),
            currency="THB",
            customer_email="atomic-paid@example.com",
            metadata_json={"session_id": "atomic-session"},
        )
        db_session.add_all([product, checkout])
        await db_session.commit()

        session_data = {
            "id": "cs_atomic_paid",
            "payment_intent": "pi_atomic_paid",
            "customer_details": {"email": "atomic-paid@example.com"},
            "metadata": {
                "organization_id": str(org.id),
                "product_id": str(product.id),
                "funnel_checkout_session_id": str(checkout.id),
            },
        }

        with patch.object(
            FunnelDeliveryService,
            "grant_delivery_access_for_order",
            new_callable=AsyncMock,
            side_effect=RuntimeError("delivery unavailable"),
        ):
            with pytest.raises(RuntimeError, match="delivery unavailable"):
                await FunnelOrderService(db_session).create_order_from_checkout_completed(
                    session_data
                )

        assert await db_session.scalar(
            select(FunnelOrder).where(
                FunnelOrder.stripe_session_id == "cs_atomic_paid"
            )
        ) is None
        assert await db_session.scalar(
            select(ConversionEvent).where(
                ConversionEvent.event_type == "purchase"
            )
        ) is None
        await db_session.refresh(checkout)
        assert checkout.status == "pending"
