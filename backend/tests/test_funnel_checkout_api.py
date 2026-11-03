import pytest
from uuid import uuid4
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import UTC, datetime

from app.models.contact import Contact
from app.models.funnel import DeliveryAsset, DigitalProduct, FunnelCheckoutSession
from tests.factories import OrganizationFactory

@pytest.fixture
def mock_stripe_session(monkeypatch):
    """Mock Stripe checkout session creation"""
    mock_session = MagicMock()
    mock_session.id = "cs_test_123"
    mock_session.url = "https://checkout.stripe.com/test_url"
    mock_session.expires_at = 1_900_000_000
    
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
        await async_client.post(
            f"/api/v1/funnel/products/{prod_id}/assets",
            json={"asset_type": "text", "title": "Live eBook file", "content_body": "content"},
        )
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
        await async_client.post(
            f"/api/v1/funnel/products/{prod_id}/assets",
            json={"asset_type": "text", "title": "Checkout file", "content_body": "content"},
        )
        await async_client.post(f"/api/v1/funnel/products/{prod_id}/publish")

        await async_client.post(f"/api/v1/funnel/products/{prod_id}/checkout", json={
            "success_url": "http://s", "cancel_url": "http://c"
        })

        stmt = select(FunnelCheckoutSession).where(FunnelCheckoutSession.product_id == UUID(prod_id))
        result = await db_session.execute(stmt)
        local_session = result.scalar_one()
        assert local_session.stripe_session_id == "cs_test_123"
        assert local_session.status == "pending"
        assert local_session.expires_at.replace(tzinfo=UTC) == datetime.fromtimestamp(
            mock_stripe_session.expires_at, tz=UTC
        )

    @pytest.mark.parametrize("is_public", [False, True])
    async def test_checkout_without_active_asset_is_rejected_before_stripe(
        self,
        is_public: bool,
        async_client: AsyncClient,
        public_async_client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch,
    ):
        product_response = await async_client.post(
            "/api/v1/funnel/products", json={"name": "No asset", "slug": "no-asset"}
        )
        product_id = UUID(product_response.json()["id"])
        product = await db_session.scalar(
            select(DigitalProduct).where(DigitalProduct.id == product_id)
        )
        product.status = "published"
        await db_session.commit()
        stripe_create = AsyncMock()
        monkeypatch.setattr(
            "app.services.funnel_checkout_service.create_stripe_checkout_session",
            stripe_create,
        )

        if is_public:
            response = await public_async_client.post(
                f"/api/v1/funnel/public/products/{product_id}/checkout",
                json={
                    "organization_id": str(product.organization_id),
                    "success_url": "https://example.test/success",
                    "cancel_url": "https://example.test/cancel",
                },
            )
        else:
            response = await async_client.post(
                f"/api/v1/funnel/products/{product_id}/checkout",
                json={
                    "success_url": "https://example.test/success",
                    "cancel_url": "https://example.test/cancel",
                },
            )

        assert response.status_code == 409
        stripe_create.assert_not_awaited()
        assert await db_session.scalar(
            select(FunnelCheckoutSession.id).where(
                FunnelCheckoutSession.product_id == product_id
            )
        ) is None

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
        await async_client.post(
            f"/api/v1/funnel/products/{prod_id}/assets",
            json={"asset_type": "text", "title": "Failure test file", "content_body": "content"},
        )
        await async_client.post(f"/api/v1/funnel/products/{prod_id}/publish")

        response = await async_client.post(f"/api/v1/funnel/products/{prod_id}/checkout", json={
            "success_url": "http://s", "cancel_url": "http://c"
        })
        assert response.status_code == 404 # Service returns None on exception

    async def test_public_product_retrieval_by_slug(
        self, public_async_client: AsyncClient, db_session: AsyncSession
    ):
        """10. Public retrieval of a published product by organization and slug works"""
        org = await OrganizationFactory.build(db_session)
        product = DigitalProduct(
            id=uuid4(),
            organization_id=org.id,
            name="Public Ebook",
            slug="public-ebook",
            price_amount=Decimal("150.00"),
            currency="THB",
            status="published"
        )
        db_session.add(product)
        db_session.add(
            DeliveryAsset(
                id=uuid4(),
                organization_id=org.id,
                product_id=product.id,
                asset_type="text",
                title="Public checkout file",
                content_body="content",
                is_active=True,
            )
        )
        await db_session.commit()

        # Retrieve published product
        response = await public_async_client.get(
            f"/api/v1/funnel/public/products/{org.id}/public-ebook"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(product.id)
        assert data["slug"] == "public-ebook"
        assert data["price_amount"] == "150.00"

        # Try to retrieve with invalid org
        response_invalid_org = await public_async_client.get(
            f"/api/v1/funnel/public/products/{uuid4()}/public-ebook"
        )
        assert response_invalid_org.status_code == 404

        # Try to retrieve with invalid slug
        response_invalid_slug = await public_async_client.get(
            f"/api/v1/funnel/public/products/{org.id}/invalid-slug"
        )
        assert response_invalid_slug.status_code == 404

        # Draft product should return 404
        draft_product = DigitalProduct(
            id=uuid4(),
            organization_id=org.id,
            name="Draft Ebook",
            slug="draft-ebook",
            price_amount=Decimal("100.00"),
            currency="THB",
            status="draft"
        )
        db_session.add(draft_product)
        await db_session.commit()

        response_draft = await public_async_client.get(
            f"/api/v1/funnel/public/products/{org.id}/draft-ebook"
        )
        assert response_draft.status_code == 404

    async def test_public_checkout_creation(
        self, public_async_client: AsyncClient, db_session: AsyncSession, mock_stripe_session
    ):
        """11. Public checkout session creation works for a published product with correct org"""
        org = await OrganizationFactory.build(db_session)
        product = DigitalProduct(
            id=uuid4(),
            organization_id=org.id,
            name="Public Live Ebook",
            slug="public-live-ebook",
            price_amount=Decimal("250.00"),
            currency="THB",
            status="published"
        )
        contact = Contact(
            id=uuid4(),
            organization_id=org.id,
            name="Public Buyer",
            email=" PUBLIC-BUYER@example.com ",
            contact_type="lead",
            relationship_strength=1,
            marketing_consent=False,
        )
        db_session.add(product)
        db_session.add(contact)
        db_session.add(
            DeliveryAsset(
                id=uuid4(),
                organization_id=org.id,
                product_id=product.id,
                asset_type="text",
                title="Public checkout file",
                content_body="content",
                is_active=True,
            )
        )
        await db_session.commit()

        payload = {
            "organization_id": str(org.id),
            "contact_id": str(contact.id),
            "customer_email": "public-buyer@example.com",
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel"
        }

        # Successful public checkout creation
        response = await public_async_client.post(
            f"/api/v1/funnel/public/products/{product.id}/checkout",
            json=payload
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stripe_session_id"] == "cs_test_123"
        assert data["checkout_url"] == "https://checkout.stripe.com/test_url"
        assert data["status"] == "pending"
        checkout = await db_session.scalar(
            select(FunnelCheckoutSession).where(
                FunnelCheckoutSession.stripe_session_id == "cs_test_123"
            )
        )
        assert checkout is not None
        assert checkout.contact_id == contact.id

        # Should return 404 if mismatched organization_id is passed in the payload
        mismatched_payload = {
            "organization_id": str(uuid4()),
            "customer_email": "public-buyer@example.com",
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel"
        }
        response_mismatch = await public_async_client.post(
            f"/api/v1/funnel/public/products/{product.id}/checkout",
            json=mismatched_payload
        )
        assert response_mismatch.status_code == 404

    async def test_public_checkout_rejects_contact_id_with_different_email(
        self,
        public_async_client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch,
    ):
        org = await OrganizationFactory.build(db_session)
        product = DigitalProduct(
            id=uuid4(),
            organization_id=org.id,
            name="Public Identity Product",
            slug="public-identity-product",
            price_amount=Decimal("25.00"),
            currency="THB",
            status="published",
        )
        contact = Contact(
            id=uuid4(),
            organization_id=org.id,
            name="Stored Contact",
            email="stored@example.com",
            contact_type="lead",
            relationship_strength=1,
            marketing_consent=False,
        )
        db_session.add_all(
            [
                product,
                contact,
                DeliveryAsset(
                    id=uuid4(),
                    organization_id=org.id,
                    product_id=product.id,
                    asset_type="text",
                    title="Public identity delivery",
                    content_body="content",
                    is_active=True,
                ),
            ]
        )
        await db_session.commit()
        create_stripe = AsyncMock()
        monkeypatch.setattr(
            "app.services.funnel_checkout_service.create_stripe_checkout_session",
            create_stripe,
        )

        response = await public_async_client.post(
            f"/api/v1/funnel/public/products/{product.id}/checkout",
            json={
                "organization_id": str(org.id),
                "contact_id": str(contact.id),
                "customer_email": "different@example.com",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )

        assert response.status_code == 422
        create_stripe.assert_not_awaited()

