"""
Test Fulfillment Service
Verify order fulfillment and entitlement management
"""
import pytest
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..services.fulfillment_service import FulfillmentService
from ..models import Product, Order, Entitlement, DeliveryEvent
from ..enums import ProductStatus, DeliveryStatus


@pytest.mark.asyncio
async def test_fulfill_order(db_session: AsyncSession):
    """Test order fulfillment creates entitlement and delivery event."""
    # Create product
    product = Product(
        name="Test Product",
        slug="test-product",
        price_cents=9900,
        status=ProductStatus.PUBLISHED,
        fulfillment_url="https://example.com/access",
    )
    db_session.add(product)
    await db_session.flush()
    
    # Create order
    order = Order(
        platform="stripe",
        platform_order_id="fulfill_test_001",
        customer_email="fulfill@example.com",
        product_id=product.id,
        amount_cents=9900,
    )
    db_session.add(order)
    await db_session.commit()
    
    # Fulfill order
    delivery_event = await FulfillmentService.fulfill_order(
        db=db_session,
        order_id=order.id,
        auto_queue_email=True,
    )
    
    assert delivery_event.id is not None
    assert delivery_event.order_id == order.id
    assert delivery_event.status == DeliveryStatus.QUEUED
    
    # Verify entitlement created
    result = await db_session.execute(
        select(Entitlement).where(Entitlement.order_id == order.id)
    )
    entitlement = result.scalar_one()
    
    assert entitlement.customer_email == "fulfill@example.com"
    assert entitlement.product_key == "test-product"
    assert entitlement.revoked_at is None


@pytest.mark.asyncio
async def test_fulfill_order_idempotent(db_session: AsyncSession):
    """Test that fulfilling same order twice is idempotent."""
    # Create product and order
    product = Product(
        name="Test Product",
        slug="test-product-idempotent",
        price_cents=9900,
        status=ProductStatus.PUBLISHED,
    )
    db_session.add(product)
    await db_session.flush()
    
    order = Order(
        platform="stripe",
        platform_order_id="idempotent_test_001",
        customer_email="idempotent@example.com",
        product_id=product.id,
        amount_cents=9900,
    )
    db_session.add(order)
    await db_session.commit()
    
    # Fulfill twice
    delivery1 = await FulfillmentService.fulfill_order(db_session, order.id)
    
    # Mark as delivered
    order.delivery_status = DeliveryStatus.DELIVERED
    await db_session.commit()
    
    delivery2 = await FulfillmentService.fulfill_order(db_session, order.id)
    
    # Should return same delivery event
    assert delivery1.id == delivery2.id


@pytest.mark.asyncio
async def test_create_entitlement(db_session: AsyncSession):
    """Test creating an entitlement."""
    # Create order
    order = Order(
        platform="stripe",
        platform_order_id="entitlement_test_001",
        customer_email="entitlement@example.com",
        amount_cents=9900,
    )
    db_session.add(order)
    await db_session.commit()
    
    # Create entitlement
    entitlement = await FulfillmentService.create_entitlement(
        db=db_session,
        order_id=order.id,
        customer_email="entitlement@example.com",
        product_key="test-product",
    )
    
    assert entitlement.id is not None
    assert entitlement.order_id == order.id
    assert entitlement.customer_email == "entitlement@example.com"
    assert entitlement.product_key == "test-product"


@pytest.mark.asyncio
async def test_revoke_entitlement(db_session: AsyncSession):
    """Test revoking an entitlement."""
    # Create order and entitlement
    order = Order(
        platform="stripe",
        platform_order_id="revoke_test_001",
        customer_email="revoke@example.com",
        amount_cents=9900,
    )
    db_session.add(order)
    await db_session.commit()
    
    entitlement = await FulfillmentService.create_entitlement(
        db=db_session,
        order_id=order.id,
        customer_email="revoke@example.com",
        product_key="test-product",
    )
    
    # Revoke entitlement
    revoked = await FulfillmentService.revoke_entitlement(
        db=db_session,
        entitlement_id=entitlement.id,
    )
    
    assert revoked.revoked_at is not None


@pytest.mark.asyncio
async def test_verify_delivery(db_session: AsyncSession):
    """Test verifying order delivery."""
    # Create product and order
    product = Product(
        name="Test Product",
        slug="verify-product",
        price_cents=9900,
        status=ProductStatus.PUBLISHED,
    )
    db_session.add(product)
    await db_session.flush()
    
    order = Order(
        platform="stripe",
        platform_order_id="verify_test_001",
        customer_email="verify@example.com",
        product_id=product.id,
        amount_cents=9900,
    )
    db_session.add(order)
    await db_session.commit()
    
    # Before fulfillment
    is_delivered = await FulfillmentService.verify_delivery(db_session, order.id)
    assert is_delivered is False
    
    # After fulfillment
    await FulfillmentService.fulfill_order(db_session, order.id)
    is_delivered = await FulfillmentService.verify_delivery(db_session, order.id)
    assert is_delivered is True


@pytest.mark.asyncio
async def test_mark_delivery_complete(db_session: AsyncSession):
    """Test marking delivery as complete."""
    # Create product and order
    product = Product(
        name="Test Product",
        slug="complete-product",
        price_cents=9900,
        status=ProductStatus.PUBLISHED,
    )
    db_session.add(product)
    await db_session.flush()
    
    order = Order(
        platform="stripe",
        platform_order_id="complete_test_001",
        customer_email="complete@example.com",
        product_id=product.id,
        amount_cents=9900,
    )
    db_session.add(order)
    await db_session.commit()
    
    # Fulfill order
    delivery_event = await FulfillmentService.fulfill_order(db_session, order.id)
    
    # Mark complete
    completed = await FulfillmentService.mark_delivery_complete(
        db=db_session,
        delivery_event_id=delivery_event.id,
    )
    
    assert completed.status == DeliveryStatus.DELIVERED
    assert completed.delivered_at is not None


@pytest.mark.asyncio
async def test_get_customer_entitlements(db_session: AsyncSession):
    """Test getting customer entitlements."""
    customer_email = "multi@example.com"
    
    # Create multiple orders and entitlements
    for i in range(3):
        order = Order(
            platform="stripe",
            platform_order_id=f"multi_test_{i}",
            customer_email=customer_email,
            amount_cents=9900,
        )
        db_session.add(order)
        await db_session.flush()
        
        await FulfillmentService.create_entitlement(
            db=db_session,
            order_id=order.id,
            customer_email=customer_email,
            product_key=f"product-{i}",
        )
    
    await db_session.commit()
    
    # Get entitlements
    entitlements = await FulfillmentService.get_customer_entitlements(
        db=db_session,
        customer_email=customer_email,
    )
    
    assert len(entitlements) == 3
    assert all(e.customer_email == customer_email for e in entitlements)
