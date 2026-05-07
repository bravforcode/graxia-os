"""
Revenue OS — Products API
Product catalog management
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
from ..models import Product
from ..enums import ProductStatus, ProductType

router = APIRouter()

# ── Schemas ──
class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    price: Decimal = Field(gt=0, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    type: ProductType = ProductType.CORE
    status: ProductStatus = ProductStatus.PUBLISHED
    sku: Optional[str] = None
    metadata: Optional[dict] = None

class ProductResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    price: Decimal
    currency: str
    type: ProductType
    status: ProductStatus
    sku: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, gt=0, decimal_places=2)
    status: Optional[ProductStatus] = None
    metadata: Optional[dict] = None

class ProductListResponse(BaseModel):
    products: List[ProductResponse]
    total: int
    page: int
    page_size: int

# ── Endpoints ──

@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_data: ProductCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create new product"""
    # Check SKU uniqueness
    if product_data.sku:
        existing = await db.execute(
            select(Product).where(Product.sku == product_data.sku)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product with this SKU already exists"
            )

    product = Product(
        name=product_data.name,
        description=product_data.description,
        price=product_data.price,
        currency=product_data.currency,
        type=product_data.type,
        status=product_data.status,
        sku=product_data.sku,
        metadata=product_data.metadata or {}
    )

    db.add(product)
    await db.commit()
    await db.refresh(product)

    return product


@router.get("/", response_model=ProductListResponse)
async def list_products(
    status: Optional[ProductStatus] = None,
    type: Optional[ProductType] = None,
    search: Optional[str] = None,
    min_price: Optional[Decimal] = None,
    max_price: Optional[Decimal] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List products with filters"""
    query = select(Product)

    if status:
        query = query.where(Product.status == status)
    if type:
        query = query.where(Product.type == type)
    if search:
        query = query.where(
            or_(
                Product.name.ilike(f"%{search}%"),
                Product.description.ilike(f"%{search}%")
            )
        )
    if min_price is not None:
        query = query.where(Product.price >= min_price)
    if max_price is not None:
        query = query.where(Product.price <= max_price)

    # Count
    count_result = await db.execute(query)
    total = len(count_result.scalars().all())

    # Paginate
    query = query.order_by(desc(Product.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    products = result.scalars().all()

    return ProductListResponse(
        products=products,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get product by ID"""
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    return product


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    update_data: ProductUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update product"""
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Update fields
    if update_data.name is not None:
        product.name = update_data.name
    if update_data.description is not None:
        product.description = update_data.description
    if update_data.price is not None:
        product.price = update_data.price
    if update_data.status is not None:
        product.status = update_data.status
    if update_data.metadata is not None:
        product.metadata.update(update_data.metadata)

    product.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(product)

    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete product (soft delete)"""
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    product.status = ProductStatus.ARCHIVED
    product.updated_at = datetime.utcnow()

    await db.commit()

    return None
