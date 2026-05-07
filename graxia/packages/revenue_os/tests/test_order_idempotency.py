"""
Test Order Idempotency
Verify that concurrent order creation is safe
"""
import pytest
import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ..services.order_service import OrderService
from ..models import Order, Product
from ..enums import ProductStatus


@pytest.mark.asyncio
async def test_order_idempotency_single(db_session: AsyncSession):
    """Test that creating the same order twice returns the same record."""
    # Create a test product
    product = Product(
        name="Test Product",
        slug="test-product",
        price_cents=9900,
        status=ProductStatus.PUBLISHED,
    )
    db_session.add(product)
    await db_session.commit()
    
    # Create order first time
    order1 = await OrderService.create_order(
        db=db_session,
        platform="stripe",
        platform_order_id="test_order_001",
        customer_email="test@example.com",
        product_id=product.id,
        amount_cents=9900,
    )
    
    # Create same order second time
    order2 = await OrderService.create_order(
        db=db_session,
        platform="stripe",
        platform_order_id="test_order_001",
        customer_email="test@example.com",
        product_id=product.id,
        amount_cents=9900,
    )
    
    # Should return the same order
    assert order1.id == order2.id
    assert order1.idempotency_key == order2.idempotency_key


@pytest.mark.asyncio
async def test_order_idempotency_concurrent(db_session: AsyncSession):
    """Test that 25 concurrent order creations result in exactly 1 order."""
    # Create a test product
    product = Product(
        name="Test Product Concurrent",
        slug="test-product-concurrent",
        price_cents=9900,
        status=ProductStatus.PUBLISHED,
    )
    db_session.add(product)
    await db_session.commit()
    
    platform_order_id = f"concurrent_test_{uuid4()}"
    
    # Create 25 concurrent order creation tasks
    tasks = [
        OrderService.create_order(
            db=db_session,
            platform="stripe",
            platform_order_id=platform_order_id,
            customer_email="concurrent@example.com",
            product_id=product.id,
            amount_cents=9900,
        )
        for _ in range(25)
    ]
    
    # Execute all concurrently
    orders = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter out exceptions (some may fail due to race conditions)
    successful_orders = [o for o in orders if isinstance(o, Order)]
    
    # All successful orders should have the same ID
    order_ids = {o.id for o in successful_orders}
    assert len(order_ids) == 1, f"Expected 1 unique order, got {len(order_ids)}"
    
    # Verify only 1 order exists in database
    from sqlalchemy import select
    result = await db_session.execute(
        select(Order).where(Order.platform_order_id == platform_order_id)
    )
    db_orders = result.scalars().all()
    assert len(db_orders) == 1


@pytest.mark.asyncio
async def test_order_creates_ledger_entry(db_session: AsyncSession):
    """Test that order creation also creates a ledger entry."""
    # Create a test product
    product = Product(
        name="Test Product Ledger",
        slug="test-product-ledger",
        price_cents=9900,
        status=ProductStatus.PUBLISHED,
    )
    db_session.add(product)
    await db_session.commit()
    
    # Create order
    order = await OrderService.create_order(
        db=db_session,
        platform="stripe",
        platform_order_id="test_ledger_001",
        customer_email="ledger@example.com",
        product_id=product.id,
        amount_cents=9900,
    )
    
    # Verify ledger entry exists
    from sqlalchemy import select
    from ..models import LedgerEntry
    
    result = await db_session.execute(
        select(LedgerEntry).where(LedgerEntry.order_id == order.id)
    )
    ledger_entries = result.scalars().all()
    
    assert len(ledger_entries) == 1
    assert ledger_entries[0].amount_cents == 9900
    assert ledger_entries[0].entry_type.value == "charge"


@pytest.mark.asyncio
async def test_order_updates_customer_stats(db_session: AsyncSession):
    """Test that order creation updates customer statistics."""
    # Create a test product
    product = Product(
        name="Test Product Stats",
        slug="test-product-stats",
        price_cents=5000,
        status=ProductStatus.PUBLISHED,
    )
    db_session.add(product)
    await db_session.commit()
    
    customer_email = "stats@example.com"
    
    # Create first order
    order1 = await OrderService.create_order(
        db=db_session,
        platform="stripe",
        platform_order_id="stats_001",
        customer_email=customer_email,
        product_id=product.id,
        amount_cents=5000,
    )
    
    # Create second order
    order2 = await OrderService.create_order(
        db=db_session,
        platform="stripe",
        platform_order_id="stats_002",
        customer_email=customer_email,
        product_id=product.id,
        amount_cents=3000,
    )
    
    # Verify customer stats
    from sqlalchemy import select
    from ..models import Customer
    
    result = await db_session.execute(
        select(Customer).where(Customer.email == customer_email)
    )
    customer = result.scalar_one()
    
    assert customer.total_spent_cents == 8000  # 5000 + 3000
    assert customer.first_purchase_at is not None
    assert customer.last_purchase_at is not None
