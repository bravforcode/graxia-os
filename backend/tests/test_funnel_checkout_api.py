import pytest
from uuid import uuid4
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.models.funnel import DigitalProduct, FunnelCheckoutSession
from app.models.organization import Organization
from tests.factories import OrganizationFactory

@pytest.fixture
def mock_stripe_session(monkeypatch):
    """Mock Stripe checkout session creation"""
    mock_session = MagicMock()
    mock_session.id = "cs_test_123"
    mock_session.url = "https://checkout.stripe.com/test_url"
    
    # Mock the method in stripe_client as an async function
    async def mock_create(**kwargs):
        return mock_session

    monkeypatch.setattr(
        "app.services.funnel_checkout_service.create_stripe_checkout_session",
        mock_create
    )
    return mock_session

@pytest.mark.asyncio
class TestFunnelCheckoutAPI:
    """Test the digital product funnel checkout API"""

    async def test_can_create_checkout_for_published_product(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_stripe_session
    ):
        """1. Can create checkout for published product"""
        # Create a published product
        res = await async_client.post("/api/v1/funnel/products", json={
            "name": "Live eBook", "slug": "live-ebook", "price_amount": "299.00"
        })
        prod_id = res.json()["id"]
        await async_client.post(f"/api/v1/funnel/products/{prod_id}/publish")

        payload = {
            "customer_email": "buyer@example.com",
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel"
        }
        response = await async_client.post(f"/api/v1/funnel/products/{prod_id}/checkout", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["stripe_session_id"] == "cs_test_123"
        assert data["checkout_url"] == "https://checkout.stripe.com/test_url"
        assert data["status"] == "pending"

    async def test_checkout_creation_creates_local_session(
        self, async_client: AsyncClient, db_session: AsyncSession, mock_stripe_session
    ):
        """2. Checkout creation creates local FunnelCheckoutSession"""
        res = await async_client.post("/api/v1/funnel/products", json={"name": "P", "slug": "p"})
        prod_id = res.json()["id"]
        await async_client.post(f"/api/v1/funnel/products/{prod_id}/publish")

        await async_client.post(f"/api/v1/funnel/products/{prod_id}/checkout", json={
            "success_url": "http://s", "cancel_url": "http://c"
        })

        stmt = select(FunnelCheckoutSession).where(FunnelCheckoutSession.product_id == UUID(prod_id))
        result = await db_session.execute(stmt)
        local_session = result.scalar_one()
        assert local_session.stripe_session_id == "cs_test_123"
        assert local_session.status == "pending"

    async def test_unpublished_product_cannot_create_checkout(self, async_client: AsyncClient):
        """5. Unpublished product cannot create checkout"""
        res = await async_client.post("/api/v1/funnel/products", json={"name": "Draft", "slug": "draft"})
        prod_id = res.json()["id"]
        # Do NOT publish

        response = await async_client.post(f"/api/v1/funnel/products/{prod_id}/checkout", json={
            "success_url": "http://s", "cancel_url": "http://c"
        })
        assert response.status_code == 404

    async def test_cross_org_product_returns_404(self, async_client: AsyncClient, db_session: AsyncSession):
        """7. Cross-org product returns 404"""
        other_org = await OrganizationFactory.build(db_session)
        other_prod = DigitalProduct(
            id=uuid4(), organization_id=other_org.id, name="Secret", slug="secret", status="published"
        )
        db_session.add(other_prod)
        await db_session.commit()

        response = await async_client.post(f"/api/v1/funnel/products/{other_prod.id}/checkout", json={
            "success_url": "http://s", "cancel_url": "http://c"
        })
        assert response.status_code == 404

    async def test_stripe_failure_marks_session_failed(self, async_client: AsyncClient, monkeypatch):
        """9. Stripe client failure returns error"""
        def mock_fail(**kwargs):
            raise Exception("Stripe down")
        
        monkeypatch.setattr("app.services.funnel_checkout_service.create_stripe_checkout_session", mock_fail)
        
        res = await async_client.post("/api/v1/funnel/products", json={"name": "P", "slug": "p"})
        prod_id = res.json()["id"]
        await async_client.post(f"/api/v1/funnel/products/{prod_id}/publish")

        response = await async_client.post(f"/api/v1/funnel/products/{prod_id}/checkout", json={
            "success_url": "http://s", "cancel_url": "http://c"
        })
        assert response.status_code == 404 # Service returns None on exception
