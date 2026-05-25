import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.funnel import (
    DigitalProduct,
    DeliveryAsset,
    FunnelCheckoutSession,
    FunnelOrder,
    FunnelOrderItem,
    DeliveryAccess,
    ConversionEvent,
)
from tests.factories import OrganizationFactory, ContactFactory


class TestFunnelFoundation:
    """Test the digital product funnel data foundation"""

    @pytest.mark.asyncio
    async def test_digital_product_creation(self, db_session):
        """Can create DigitalProduct with organization_id"""
        org = await OrganizationFactory.build(db_session)
        
        product = DigitalProduct(
            id=uuid4(),
            organization_id=org.id,
            name="AI Starter Kit",
            slug="ai-starter-kit",
            description="A great kit for AI developers",
            price_amount=Decimal("499.00"),
            currency="THB",
            status="published",
            product_type="kit",
        )
        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(product)
        
        assert product.name == "AI Starter Kit"
        assert product.organization_id == org.id
        assert product.price_amount == Decimal("499.00")

    @pytest.mark.asyncio
    async def test_slug_unique_per_organization(self, db_session):
        """Slug must be unique per organization"""
        org = await OrganizationFactory.build(db_session)
        
        product1 = DigitalProduct(
            id=uuid4(),
            organization_id=org.id,
            name="Product 1",
            slug="duplicate-slug",
            price_amount=Decimal("100.00"),
        )
        db_session.add(product1)
        await db_session.commit()
        
        product2 = DigitalProduct(
            id=uuid4(),
            organization_id=org.id,
            name="Product 2",
            slug="duplicate-slug",
            price_amount=Decimal("200.00"),
        )
        db_session.add(product2)
        
        with pytest.raises(IntegrityError):
            await db_session.commit()
        
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_same_slug_allowed_different_orgs(self, db_session):
        """Same slug allowed across different organizations"""
        org1 = await OrganizationFactory.build(db_session)
        org2 = await OrganizationFactory.build(db_session)
        
        product1 = DigitalProduct(
            id=uuid4(),
            organization_id=org1.id,
            name="Product 1",
            slug="shared-slug",
            price_amount=Decimal("100.00"),
        )
        product2 = DigitalProduct(
            id=uuid4(),
            organization_id=org2.id,
            name="Product 2",
            slug="shared-slug",
            price_amount=Decimal("100.00"),
        )
        db_session.add_all([product1, product2])
        await db_session.commit()
        
        assert product1.slug == product2.slug
        assert product1.organization_id != product2.organization_id

    @pytest.mark.asyncio
    async def test_attach_delivery_asset(self, db_session):
        """Can attach DeliveryAsset to product"""
        org = await OrganizationFactory.build(db_session)
        product = DigitalProduct(
            id=uuid4(),
            organization_id=org.id,
            name="Product with Assets",
            slug="asset-prod",
            price_amount=Decimal("100.00"),
        )
        db_session.add(product)
        await db_session.commit()
        
        asset = DeliveryAsset(
            id=uuid4(),
            organization_id=org.id,
            product_id=product.id,
            asset_type="file",
            title="Starter Guide PDF",
            storage_path="products/guide.pdf",
        )
        db_session.add(asset)
        await db_session.commit()
        await db_session.refresh(product)
        
        assert len(product.assets) == 1
        assert product.assets[0].title == "Starter Guide PDF"

    @pytest.mark.asyncio
    async def test_checkout_session_creation(self, db_session):
        """Can create CheckoutSession for product"""
        org = await OrganizationFactory.build(db_session)
        product = DigitalProduct(
            id=uuid4(),
            organization_id=org.id,
            name="Test Prod",
            slug="test-prod",
            price_amount=Decimal("100.00"),
        )
        db_session.add(product)
        await db_session.commit()
        
        session = FunnelCheckoutSession(
            id=uuid4(),
            organization_id=org.id,
            product_id=product.id,
            amount=product.price_amount,
            currency=product.currency,
            status="created",
            stripe_session_id=f"cs_{uuid4().hex}",
        )
        db_session.add(session)
        await db_session.commit()
        
        assert session.product_id == product.id
        assert session.status == "created"

    @pytest.mark.asyncio
    async def test_order_and_item_creation(self, db_session):
        """Can create Order and OrderItem"""
        org = await OrganizationFactory.build(db_session)
        product = DigitalProduct(
            id=uuid4(),
            organization_id=org.id,
            name="Test Order Prod",
            slug="order-prod",
            price_amount=Decimal("1000.00"),
        )
        db_session.add(product)
        await db_session.commit()
        
        order = FunnelOrder(
            id=uuid4(),
            organization_id=org.id,
            status="pending",
            subtotal_amount=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
            currency="THB",
            customer_email="customer@test.com",
        )
        db_session.add(order)
        await db_session.commit()
        
        item = FunnelOrderItem(
            id=uuid4(),
            organization_id=org.id,
            order_id=order.id,
            product_id=product.id,
            quantity=1,
            unit_amount=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(order)
        
        assert len(order.items) == 1
        assert order.items[0].product_id == product.id

    @pytest.mark.asyncio
    async def test_delivery_access_after_order(self, db_session):
        """Can grant DeliveryAccess after order"""
        org = await OrganizationFactory.build(db_session)
        product = DigitalProduct(
            id=uuid4(),
            organization_id=org.id,
            name="Access Prod",
            slug="access-prod",
            price_amount=Decimal("10.00"),
        )
        db_session.add(product)
        await db_session.commit()
        
        order = FunnelOrder(
            id=uuid4(),
            organization_id=org.id,
            status="paid",
            subtotal_amount=Decimal("10.00"),
            total_amount=Decimal("10.00"),
        )
        db_session.add(order)
        await db_session.commit()
        
        access = DeliveryAccess(
            id=uuid4(),
            organization_id=org.id,
            order_id=order.id,
            product_id=product.id,
            status="active",
            expires_at=datetime.now(UTC) + timedelta(days=365),
        )
        db_session.add(access)
        await db_session.commit()
        
        assert access.status == "active"
        assert access.order_id == order.id

    @pytest.mark.asyncio
    async def test_conversion_event_creation(self, db_session):
        """Can create ConversionEvent"""
        org = await OrganizationFactory.build(db_session)
        
        event = ConversionEvent(
            id=uuid4(),
            organization_id=org.id,
            event_type="page_view",
            source="google",
            medium="organic",
            occurred_at=datetime.now(UTC),
        )
        db_session.add(event)
        await db_session.commit()
        
        assert event.event_type == "page_view"
        assert event.organization_id == org.id

    @pytest.mark.asyncio
    async def test_cross_org_isolation(self, db_session):
        """Cross-org query must not leak products"""
        org1 = await OrganizationFactory.build(db_session)
        org2 = await OrganizationFactory.build(db_session)
        
        p1 = DigitalProduct(
            id=uuid4(),
            organization_id=org1.id,
            name="Org 1 Prod",
            slug="p1",
            price_amount=Decimal("100.00"),
        )
        p2 = DigitalProduct(
            id=uuid4(),
            organization_id=org2.id,
            name="Org 2 Prod",
            slug="p2",
            price_amount=Decimal("200.00"),
        )
        db_session.add_all([p1, p2])
        await db_session.commit()
        
        # Query for org1 should only return p1
        stmt = select(DigitalProduct).where(DigitalProduct.organization_id == org1.id)
        results = (await db_session.execute(stmt)).scalars().all()
        
        assert len(results) == 1
        assert results[0].name == "Org 1 Prod"

    @pytest.mark.asyncio
    async def test_constraints_reject_invalid_data(self, db_session):
        """Constraints reject negative price if enforced"""
        org = await OrganizationFactory.build(db_session)
        
        # SQLAlchemy CheckConstraint is enforced at DB level
        # For some DBs (SQLite/Postgres) this might only trigger on commit
        product = DigitalProduct(
            id=uuid4(),
            organization_id=org.id,
            name="Invalid Price",
            slug="invalid-price",
            price_amount=Decimal("-10.00"),
        )
        db_session.add(product)
        
        with pytest.raises(IntegrityError):
            await db_session.commit()
        
        await db_session.rollback()
