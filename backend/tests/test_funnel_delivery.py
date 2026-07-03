import pytest
import secrets
import hashlib
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import DigitalProduct, FunnelCheckoutSession, FunnelOrder, FunnelOrderItem, DeliveryAsset, DeliveryAccess
from app.models.organization import Organization
from tests.factories import OrganizationFactory, UserFactory

@pytest.mark.asyncio
class TestFunnelDelivery:
    """Test the digital product delivery service and API"""

    async def test_paid_order_grants_delivery_access(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """1. Paid order grants delivery access"""
        # Retrieve organization created by the async_client fixture
        res = await db_session.execute(select(Organization))
        org = res.scalars().first()
        org_id = org.id
        
        # 1. Setup Product and Asset
        prod = DigitalProduct(
            id=uuid4(), organization_id=org_id, name="Test Prod", slug="test-prod",
            price_amount=Decimal("100.00"), currency="THB", status="published"
        )
        asset = DeliveryAsset(
            id=uuid4(), organization_id=org_id, product_id=prod.id,
            title="Ebook", asset_type="text", content_body="Secret Knowledge", is_active=True
        )
        db_session.add_all([prod, asset])
        
        # 2. Setup Paid Order
        order = FunnelOrder(
            id=uuid4(), organization_id=org_id, status="paid", 
            subtotal_amount=Decimal("100.00"), total_amount=Decimal("100.00"), currency="THB"
        )
        db_session.add(order)
        await db_session.flush()
        
        item = FunnelOrderItem(
            organization_id=org_id, order_id=order.id, product_id=prod.id,
            quantity=1, unit_amount=Decimal("100.00"), total_amount=Decimal("100.00"), currency="THB"
        )
        db_session.add(item)
        await db_session.commit()

        # 3. Call API to grant delivery
        response = await async_client.post(
            f"/api/v1/funnel/orders/{order.id}/grant-delivery"
        )
        assert response.status_code == 201
        data = response.json()
        assert len(data) == 1
        raw_token = data[0]["raw_token"]
        assert raw_token is not None

        # 4. Verify DB record
        stmt = select(DeliveryAccess).where(DeliveryAccess.order_id == order.id)
        res = await db_session.execute(stmt)
        access = res.scalar_one()
        assert access.product_id == prod.id
        assert access.asset_id == asset.id
        assert access.access_token_hash == hashlib.sha256(raw_token.encode()).hexdigest()

    async def test_unpaid_order_cannot_grant_access(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """2. Unpaid order cannot grant access"""
        # Retrieve organization created by the async_client fixture
        res = await db_session.execute(select(Organization))
        org = res.scalars().first()
        org_id = org.id
        order = FunnelOrder(
            id=uuid4(), organization_id=org_id, status="pending", 
            subtotal_amount=Decimal("100.00"), total_amount=Decimal("100.00"), currency="THB"
        )
        db_session.add(order)
        await db_session.commit()

        response = await async_client.post(
            f"/api/v1/funnel/orders/{order.id}/grant-delivery"
        )
        assert response.status_code == 201
        assert response.json() == []

    async def test_delivery_token_lookup_and_consumption(
        self, public_async_client: AsyncClient, db_session: AsyncSession
    ):
        """4. Token lookup works and 7. max_downloads enforced"""
        org = await OrganizationFactory.build(db_session)
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="P", slug="p", 
            price_amount=Decimal("1.00"), status="published"
        )
        asset = DeliveryAsset(
            id=uuid4(), organization_id=org.id, product_id=prod.id,
            title="L", asset_type="external_link", external_url="https://link.com", is_active=True
        )
        order = FunnelOrder(
            id=uuid4(), organization_id=org.id, status="paid", 
            subtotal_amount=Decimal("1.00"), total_amount=Decimal("1.00"), currency="THB"
        )
        db_session.add_all([prod, asset, order])
        await db_session.flush()

        raw_token = secrets.token_urlsafe(32)
        access = DeliveryAccess(
            id=uuid4(), organization_id=org.id, order_id=order.id, product_id=prod.id,
            asset_id=asset.id, access_token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            status="active", max_downloads=2, download_count=0
        )
        db_session.add(access)
        await db_session.commit()

        # Consume 1
        resp = await public_async_client.get(f"/api/v1/funnel/delivery/{raw_token}")
        assert resp.status_code == 200
        assert resp.json()["external_url"] == "https://link.com"
        assert resp.json()["downloads_remaining"] == 1

        # Consume 2
        resp = await public_async_client.get(f"/api/v1/funnel/delivery/{raw_token}")
        assert resp.status_code == 200
        assert resp.json()["downloads_remaining"] == 0

        # Consume 3 -> Limit exceeded
        resp = await public_async_client.get(f"/api/v1/funnel/delivery/{raw_token}")
        assert resp.status_code == 404
        assert "Invalid or expired" in resp.json()["detail"]

    async def test_expired_token_fails(
        self, public_async_client: AsyncClient, db_session: AsyncSession
    ):
        """5. Expired token fails"""
        org = await OrganizationFactory.build(db_session)
        prod = DigitalProduct(
            id=uuid4(), organization_id=org.id, name="P", slug="p4", 
            price_amount=Decimal("1.00"), status="published"
        )
        asset = DeliveryAsset(
            id=uuid4(), organization_id=org.id, product_id=prod.id,
            title="A", asset_type="text", content_body="C", is_active=True
        )
        order = FunnelOrder(
            id=uuid4(), organization_id=org.id, status="paid", 
            subtotal_amount=Decimal("1.00"), total_amount=Decimal("1.00"), currency="THB"
        )
        db_session.add_all([prod, asset, order])
        await db_session.flush()

        raw_token = "expired_token"
        access = DeliveryAccess(
            id=uuid4(), organization_id=org.id, order_id=order.id, product_id=prod.id,
            asset_id=asset.id, access_token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            status="active", max_downloads=10, download_count=0,
            expires_at=datetime.now() - timedelta(hours=1)
        )
        db_session.add(access)
        await db_session.commit()

        resp = await public_async_client.get(f"/api/v1/funnel/delivery/{raw_token}")
        assert resp.status_code == 404

    async def test_cross_org_access_fails(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """10. Cross-org access fails"""
        org1 = await OrganizationFactory.build(db_session)
        org2 = await OrganizationFactory.build(db_session)
        
        # Order in org1
        order1 = FunnelOrder(
            id=uuid4(), organization_id=org1.id, status="paid", 
            subtotal_amount=Decimal("1"), total_amount=Decimal("1"), currency="THB"
        )
        db_session.add(order1)
        await db_session.commit()

        # async_client is already authenticated as an admin in its own org (not org1)
        response = await async_client.post(
            f"/api/v1/funnel/orders/{order1.id}/grant-delivery"
        )
        # Should return empty list because order not found for client's current org
        assert response.json() == []
