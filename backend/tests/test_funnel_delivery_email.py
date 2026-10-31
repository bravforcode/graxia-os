"""Run directly: isolated temporary SQLite and mocked provider, no shared conftest."""
from pathlib import Path
if __name__ == '__main__':
    import os, sys, socket, ipaddress, faulthandler
    from contextlib import ExitStack
    from unittest.mock import patch
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.update(TESTING='true',APP_ENV='testing',DATABASE_URL='sqlite+aiosqlite:///:memory:',
        REDIS_ENABLED='false',REDIS_URL='',CELERY_BROKER_URL='',RESEND_API_KEY='',STRIPE_SECRET_KEY='',
        SECRET_KEY='synthetic-offline-secret-not-production',
        ENCRYPTION_KEY='MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    from pydantic_settings.sources import DotEnvSettingsSource
    import pytest
    original_connect=socket.socket.connect
    def local_connect(sock,address):
        if isinstance(address,tuple) and ipaddress.ip_address(address[0]).is_loopback:
            return original_connect(sock,address)
        raise RuntimeError('fixture_network_disabled')
    faulthandler.dump_traceback_later(90,exit=True)
    with ExitStack() as guard:
        guard.enter_context(patch.object(DotEnvSettingsSource,'_read_env_files',return_value={}))
        guard.enter_context(patch.object(socket.socket,'connect',new=local_connect))
        guard.enter_context(patch.object(socket.socket,'connect_ex',side_effect=RuntimeError('fixture_network_disabled')))
        raise SystemExit(pytest.main(['--noconftest','-p','no:cacheprovider','-p','pytest_asyncio.plugin',
            '-o','addopts=','-q',str(Path(__file__).resolve())]))

import pytest
import pytest_asyncio
import tempfile
import hashlib
from uuid import uuid4
from decimal import Decimal
from unittest.mock import patch, AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
import app.models
from app.models.base import Base
from app.models.delivery_email_event import DeliveryEmailEvent
from app.database import get_db
from app.config import settings
from app.api import funnel_webhooks
from app.services.email_service import email_service

from app.models.funnel import DigitalProduct, FunnelCheckoutSession, FunnelOrder, DeliveryAccess, DeliveryAsset
from app.services.funnel_delivery_email_service import FunnelDeliveryEmailService, DeliveryEmailOutcome
from tests.factories import OrganizationFactory

@pytest_asyncio.fixture
async def db_session():
    with tempfile.TemporaryDirectory(prefix='graxia-delivery-contract-') as directory:
        engine=create_async_engine('sqlite+aiosqlite:///'+str(Path(directory)/'fixture.sqlite'))
        factory=async_sessionmaker(engine,expire_on_commit=False)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            with patch('app.database.AsyncSessionLocal',factory):
                async with factory() as session:
                    yield session
        finally:
            await engine.dispose()
    assert not Path(directory).exists(), 'isolated_database_cleanup_failed'

@pytest_asyncio.fixture
async def async_client(db_session):
    app=FastAPI()
    app.include_router(funnel_webhooks.router,prefix='/api/v1/funnel/webhooks')
    async def fixture_db(): yield db_session
    app.dependency_overrides[get_db]=fixture_db
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://fixture.invalid') as client:
        yield client

@pytest.fixture(autouse=True)
def provider_boundary():
    provider=AsyncMock(return_value={'status':'sent','id':'fixture_provider_accepted'})
    with patch.object(email_service,'send_email',provider), \
            patch.object(funnel_webhooks,'_forward_to_revenue_os',AsyncMock()), \
            patch('app.services.automation_email_service.AutomationEmailService.trigger_post_purchase',
                AsyncMock(return_value={'status':'suppressed','id':None})), \
            patch.object(settings,'STRIPE_WEBHOOK_SECRET','synthetic-signature-fixture'), \
            patch.object(settings,'REDIS_URL',''),patch.object(settings,'CELERY_BROKER_URL',''):
        yield provider

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

    async def test_email_service_structures_links_and_names(self, db_session: AsyncSession,provider_boundary):
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
            ,stripe_session_id='cs_synthetic_direct'
        )
        db_session.add_all([prod, asset, order])
        await db_session.commit()

        access = DeliveryAccess(
            id=uuid4(), organization_id=org.id, order_id=order.id, product_id=prod.id,
            asset_id=asset.id, access_token_hash=hashlib.sha256(b'secret_token_123').hexdigest(), status="active", download_count=0
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
        assert type(success) is DeliveryEmailOutcome
        assert success.status == 'sent' and success.provider_reference == 'fixture_provider_accepted'
        provider_boundary.assert_awaited_once()
        
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
        row=await db_session.scalar(select(DeliveryEmailEvent))
        assert row.idempotency_key == f'funnel_delivery_session:{org.id}:'+hashlib.sha256(order.stripe_session_id.encode()).hexdigest()

    async def test_webhook_triggers_email_delivery(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_webhook_signature,provider_boundary
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
            status="pending", amount=Decimal("50.00"), currency="USD", customer_email="buyer_email@test.com", stripe_session_id="cs_webhook_email_test"
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
        assert response.json()['delivery_email_status'] == 'sent'
        assert response.json()['delivery_email_provider_reference'] == 'fixture_provider_accepted'
        provider_boundary.assert_awaited_once()

        # Verify email is queued
        assert len(FunnelDeliveryEmailService.sent_emails) == 1
        sent = FunnelDeliveryEmailService.sent_emails[0]
        assert sent["to"] == "buyer_email@test.com"
        assert sent["template_data"]["delivery_items"][0]["product_name"] == "Membership Premium"

    @pytest.mark.parametrize('provider_result,expected',[
        ({'status':'sent','id':None},'unknown'),
        ({'status':'failed','error':'TimeoutError'},'unknown'),
        ({'status':'suppressed','id':None},'suppressed'),
        (TimeoutError('synthetic timeout'),'unknown'),
    ])
    async def test_email_error_handled_gracefully(self, db_session: AsyncSession,provider_boundary,provider_result,expected):
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
            ,stripe_session_id='cs_synthetic_error'
        )
        db_session.add_all([prod, asset, order])
        await db_session.commit()

        access = DeliveryAccess(
            id=uuid4(), organization_id=org.id, order_id=order.id, product_id=prod.id,
            asset_id=asset.id, access_token_hash=hashlib.sha256(b'secret_token_123').hexdigest(), status="active", download_count=0
        )
        db_session.add(access)
        await db_session.commit()

        email_service = FunnelDeliveryEmailService(db_session)
        
        if isinstance(provider_result,Exception):
            provider_boundary.side_effect=provider_result
        else:
            provider_boundary.return_value=provider_result
        for _ in range(2):
            success = await email_service.send_delivery_links(
                organization_id=org.id,
                order_id=order.id,
                customer_email="customer@example.com",
                delivery_accesses=[(access, "secret_token_123")]
            )
            assert type(success) is DeliveryEmailOutcome
            assert success.status == expected and success.provider_reference is None
        provider_boundary.assert_awaited_once()
        assert FunnelDeliveryEmailService.sent_emails == []
        row=await db_session.scalar(select(DeliveryEmailEvent))
        assert row.sent_at is None and 'provider_reference' not in row.metadata_json
