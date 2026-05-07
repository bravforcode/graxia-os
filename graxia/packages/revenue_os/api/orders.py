"""
Revenue OS — Orders API
Production-ready order management with idempotency
"""
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc
from pydantic import BaseModel, Field

from ..db import get_db
from ..models import Order, Product
from ..enums import OrderStatus

router = APIRouter()

# ── Pydantic Schemas ──
class OrderLineItemCreate(BaseModel):
    product_id: UUID
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(gt=0, decimal_places=2)
    metadata: Optional[dict] = None

class OrderCreate(BaseModel):
    platform: str = Field(..., description="stripe | gumroad | paypal | manual")
    platform_order_id: str
    customer_email: str
    customer_name: Optional[str] = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    line_items: List[OrderLineItemCreate]
    idempotency_key: Optional[str] = None
    metadata: Optional[dict] = None

class OrderResponse(BaseModel):
    id: UUID
    platform: str
    platform_order_id: str
    customer_email: str
    customer_name: Optional[str]
    amount_cents: int
    currency: str
    status: OrderStatus
    created_at: datetime

    class Config:
        from_attributes = True

class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    customer_email: Optional[str] = None
    metadata: Optional[dict] = None

class OrderListResponse(BaseModel):
    orders: List[OrderResponse]
    total: int
    page: int
    page_size: int

class RevenueSummary(BaseModel):
    period: str
    total_revenue: Decimal
    total_orders: int
    average_order_value: Decimal
    refund_amount: Decimal
    net_revenue: Decimal

# ── API Endpoints ──

@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create new order with idempotency check"""
    # Check idempotency
    if order_data.idempotency_key:
        existing = await db.execute(
            select(Order).where(Order.idempotency_key == order_data.idempotency_key)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Order with this idempotency key already exists"
            )

    # Check duplicate platform order
    existing = await db.execute(
        select(Order).where(
            and_(
                Order.platform == order_data.platform,
                Order.platform_order_id == order_data.platform_order_id
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order with this platform_order_id already exists"
        )

    # Calculate amount in cents from line items
    total_amount = sum(
        item.quantity * item.unit_price
        for item in order_data.line_items
    ) if order_data.line_items else Decimal("0")
    amount_cents = int(total_amount * 100)

    # Create order
    order = Order(
        platform=order_data.platform,
        platform_order_id=order_data.platform_order_id,
        customer_email=order_data.customer_email,
        customer_name=order_data.customer_name,
        currency=order_data.currency,
        amount_cents=amount_cents,
        idempotency_key=order_data.idempotency_key or f"manual_{uuid4()}",
        metadata_={
            "line_items": [
                {
                    "product_id": str(item.product_id),
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "metadata": item.metadata
                }
                for item in order_data.line_items
            ] if order_data.line_items else [],
            **(order_data.metadata or {})
        },
        status=OrderStatus.PENDING
    )

    db.add(order)
    await db.commit()
    await db.refresh(order)

    return order


@router.get("/", response_model=OrderListResponse)
async def list_orders(
    status: Optional[OrderStatus] = None,
    platform: Optional[str] = None,
    customer_email: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List orders with filters and pagination"""
    query = select(Order)

    # Apply filters
    if status:
        query = query.where(Order.status == status)
    if platform:
        query = query.where(Order.platform == platform)
    if customer_email:
        query = query.where(Order.customer_email.ilike(f"%{customer_email}%"))
    if start_date:
        query = query.where(Order.created_at >= start_date)
    if end_date:
        query = query.where(Order.created_at <= end_date)

    # Count total
    count_query = select(Order.id)
    if status:
        count_query = count_query.where(Order.status == status)
    if platform:
        count_query = count_query.where(Order.platform == platform)
    if customer_email:
        count_query = count_query.where(Order.customer_email.ilike(f"%{customer_email}%"))
    if start_date:
        count_query = count_query.where(Order.created_at >= start_date)
    if end_date:
        count_query = count_query.where(Order.created_at <= end_date)

    total_result = await db.execute(count_query)
    total = len(total_result.scalars().all())

    # Apply pagination
    query = query.order_by(desc(Order.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    orders = result.scalars().all()

    return OrderListResponse(
        orders=orders,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get single order by ID"""
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    return order


@router.patch("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: UUID,
    update_data: OrderUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update order status and details"""
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    # Update fields
    if update_data.status is not None:
        order.status = update_data.status
    if update_data.customer_email is not None:
        order.customer_email = update_data.customer_email
    if update_data.metadata is not None:
        order.metadata_.update(update_data.metadata)

    order.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(order)

    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete order (soft delete via status change)"""
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    order.status = OrderStatus.CANCELLED
    order.updated_at = datetime.utcnow()

    await db.commit()

    return None


@router.get("/summary/daily", response_model=RevenueSummary)
async def get_daily_summary(
    date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get daily revenue summary"""
    if date is None:
        date = datetime.utcnow()

    # This would query aggregated data
    # Simplified for now
    return RevenueSummary(
        period=date.strftime("%Y-%m-%d"),
        total_revenue=Decimal("0.00"),
        total_orders=0,
        average_order_value=Decimal("0.00"),
        refund_amount=Decimal("0.00"),
        net_revenue=Decimal("0.00")
    )
