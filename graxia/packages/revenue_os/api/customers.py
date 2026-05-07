"""
Revenue OS — Customers API
Customer management and analytics
"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from pydantic import BaseModel, Field, EmailStr

from ..db import get_db
from ..models import Customer, Order

router = APIRouter()

# ── Schemas ──
class CustomerCreate(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None
    metadata: Optional[dict] = None

class CustomerResponse(BaseModel):
    id: UUID
    email: str
    name: Optional[str]
    phone: Optional[str]
    total_orders: int
    total_spent: float
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    metadata: Optional[dict] = None

class CustomerAnalytics(BaseModel):
    customer_id: UUID
    total_orders: int
    total_revenue: float
    average_order_value: float
    first_order_date: Optional[datetime]
    last_order_date: Optional[datetime]
    lifetime_value: float

class CustomerListResponse(BaseModel):
    customers: List[CustomerResponse]
    total: int
    page: int
    page_size: int

# ── Endpoints ──

@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: CustomerCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create new customer or return existing"""
    # Check if customer exists
    existing = await db.execute(
        select(Customer).where(Customer.email == customer_data.email)
    )
    customer = existing.scalar_one_or_none()
    
    if customer:
        # Update if new info provided
        if customer_data.name and not customer.name:
            customer.name = customer_data.name
        if customer_data.phone and not customer.phone:
            customer.phone = customer_data.phone
        if customer_data.metadata:
            customer.metadata.update(customer_data.metadata)
        
        await db.commit()
        await db.refresh(customer)
        return customer
    
    # Create new
    customer = Customer(
        email=customer_data.email,
        name=customer_data.name,
        phone=customer_data.phone,
        metadata=customer_data.metadata or {},
        total_orders=0,
        total_spent=0.0
    )
    
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    
    return customer


@router.get("/", response_model=CustomerListResponse)
async def list_customers(
    search: Optional[str] = None,
    min_orders: Optional[int] = None,
    min_spent: Optional[float] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List customers with filters"""
    query = select(Customer)
    
    if search:
        query = query.where(
            func.lower(Customer.email).contains(search.lower()) |
            func.lower(Customer.name).contains(search.lower())
        )
    if min_orders:
        query = query.where(Customer.total_orders >= min_orders)
    if min_spent:
        query = query.where(Customer.total_spent >= min_spent)
    
    # Count
    count_result = await db.execute(query)
    total = len(count_result.scalars().all())
    
    # Paginate
    query = query.order_by(desc(Customer.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    customers = result.scalars().all()
    
    return CustomerListResponse(
        customers=customers,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get customer by ID"""
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    return customer


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID,
    update_data: CustomerUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update customer"""
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    if update_data.name is not None:
        customer.name = update_data.name
    if update_data.phone is not None:
        customer.phone = update_data.phone
    if update_data.metadata is not None:
        customer.metadata.update(update_data.metadata)
    
    customer.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(customer)
    
    return customer


@router.get("/{customer_id}/analytics", response_model=CustomerAnalytics)
async def get_customer_analytics(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get customer analytics"""
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    # Get order stats
    orders_result = await db.execute(
        select(Order).where(
            Order.customer_email == customer.email,
            Order.status != "cancelled"
        ).order_by(Order.created_at)
    )
    orders = orders_result.scalars().all()
    
    total_revenue = sum(float(o.total_amount) for o in orders if o.status != "refunded")
    
    return CustomerAnalytics(
        customer_id=customer.id,
        total_orders=len(orders),
        total_revenue=total_revenue,
        average_order_value=total_revenue / len(orders) if orders else 0,
        first_order_date=orders[0].created_at if orders else None,
        last_order_date=orders[-1].created_at if orders else None,
        lifetime_value=total_revenue
    )
