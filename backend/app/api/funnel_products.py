import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.tenant import get_org
from app.models.organization import Organization
from app.services.funnel_product_service import FunnelProductService
from app.services.funnel_checkout_service import FunnelCheckoutService
from app.schemas.funnel import (
    DigitalProductRead,
    DigitalProductCreate,
    DigitalProductUpdate,
    DeliveryAssetRead,
    DeliveryAssetCreate,
    DeliveryAssetUpdate,
    FunnelCheckoutCreate,
    FunnelCheckoutCreatePublic,
    FunnelCheckoutRead,
)

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_funnel_service(db: AsyncSession = Depends(get_db)) -> FunnelProductService:
    return FunnelProductService(db)

async def get_checkout_service(db: AsyncSession = Depends(get_db)) -> FunnelCheckoutService:
    return FunnelCheckoutService(db)

# Products Endpoints

@router.post("/products", response_model=DigitalProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: DigitalProductCreate,
    org: Organization = Depends(get_org),
    service: FunnelProductService = Depends(get_funnel_service),
):
    """Create a new digital product."""
    return await service.create_product(org.id, payload)

@router.get("/products", response_model=List[DigitalProductRead])
async def list_products(
    include_archived: bool = Query(False),
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    org: Organization = Depends(get_org),
    service: FunnelProductService = Depends(get_funnel_service),
):
    """List products for the current organization."""
    return await service.list_products(org.id, include_archived, limit, offset)

@router.get("/products/{product_id}", response_model=DigitalProductRead)
async def get_product(
    product_id: UUID,
    org: Organization = Depends(get_org),
    service: FunnelProductService = Depends(get_funnel_service),
):
    """Get product details."""
    product = await service.get_product(org.id, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@router.patch("/products/{product_id}", response_model=DigitalProductRead)
async def update_product(
    product_id: UUID,
    payload: DigitalProductUpdate,
    org: Organization = Depends(get_org),
    service: FunnelProductService = Depends(get_funnel_service),
):
    """Update product details."""
    product = await service.update_product(org.id, product_id, payload)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@router.post("/products/{product_id}/publish", response_model=DigitalProductRead)
async def publish_product(
    product_id: UUID,
    org: Organization = Depends(get_org),
    service: FunnelProductService = Depends(get_funnel_service),
):
    """Publish a digital product."""
    product = await service.publish_product(org.id, product_id)
    if not product:
        # If product exists but validation failed, we might want 400, 
        # but if it doesn't exist, 404. Service returns None for both.
        # Let's check existence first to be precise if needed, 
        # or just 404 as per prompt "Cross-org product/asset access must return 404".
        raise HTTPException(status_code=404, detail="Product not found or validation failed")
    return product

@router.post("/products/{product_id}/archive", response_model=DigitalProductRead)
async def archive_product(
    product_id: UUID,
    org: Organization = Depends(get_org),
    service: FunnelProductService = Depends(get_funnel_service),
):
    """Archive a digital product."""
    product = await service.archive_product(org.id, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: UUID,
    org: Organization = Depends(get_org),
    service: FunnelProductService = Depends(get_funnel_service),
):
    """Soft-delete a digital product."""
    success = await service.delete_or_soft_delete_product(org.id, product_id)
    if not success:
        raise HTTPException(status_code=404, detail="Product not found")
    return

# Checkout Endpoints

@router.post("/products/{product_id}/checkout", response_model=FunnelCheckoutRead)
async def create_checkout_session(
    product_id: UUID,
    payload: FunnelCheckoutCreate,
    org: Organization = Depends(get_org),
    service: FunnelCheckoutService = Depends(get_checkout_service),
):
    """Create a Stripe checkout session for a product."""
    result = await service.create_checkout_session(
        organization_id=org.id,
        product_id=product_id,
        payload=payload,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Product not found or not published")
    return result

# Delivery Assets Endpoints

@router.post("/products/{product_id}/assets", response_model=DeliveryAssetRead, status_code=status.HTTP_201_CREATED)
async def create_asset(
    product_id: UUID,
    payload: DeliveryAssetCreate,
    org: Organization = Depends(get_org),
    service: FunnelProductService = Depends(get_funnel_service),
):
    """Create a delivery asset for a product."""
    asset = await service.create_delivery_asset(org.id, product_id, payload)
    if not asset:
        raise HTTPException(status_code=404, detail="Product not found")
    return asset

@router.get("/products/{product_id}/assets", response_model=List[DeliveryAssetRead])
async def list_assets(
    product_id: UUID,
    org: Organization = Depends(get_org),
    service: FunnelProductService = Depends(get_funnel_service),
):
    """List assets for a product."""
    # This automatically verifies product ownership through the service
    return await service.list_delivery_assets(org.id, product_id)

@router.get("/assets/{asset_id}", response_model=DeliveryAssetRead)
async def get_asset(
    asset_id: UUID,
    org: Organization = Depends(get_org),
    service: FunnelProductService = Depends(get_funnel_service),
):
    """Get delivery asset details."""
    asset = await service.get_delivery_asset(org.id, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset

@router.patch("/assets/{asset_id}", response_model=DeliveryAssetRead)
async def update_asset(
    asset_id: UUID,
    payload: DeliveryAssetUpdate,
    org: Organization = Depends(get_org),
    service: FunnelProductService = Depends(get_funnel_service),
):
    """Update delivery asset details."""
    asset = await service.update_delivery_asset(org.id, asset_id, payload)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset

@router.post("/assets/{asset_id}/deactivate", response_model=DeliveryAssetRead)
async def deactivate_asset(
    asset_id: UUID,
    org: Organization = Depends(get_org),
    service: FunnelProductService = Depends(get_funnel_service),
):
    """Deactivate a delivery asset."""
    success = await service.deactivate_delivery_asset(org.id, asset_id)
    if not success:
        raise HTTPException(status_code=404, detail="Asset not found")
    return await service.get_delivery_asset(org.id, asset_id)


# Public Endpoints (Whitelisted from general auth in middleware)

@router.get("/public/products/{organization_id}/{slug}", response_model=DigitalProductRead)
async def get_public_product_by_slug(
    organization_id: UUID,
    slug: str,
    service: FunnelProductService = Depends(get_funnel_service),
):
    """Retrieve a published product by organization and slug."""
    product = await service.get_product_by_slug(organization_id, slug)
    if not product or product.status != "published":
        raise HTTPException(status_code=404, detail="Product not found or not published")
    return product

@router.post("/public/products/{product_id}/checkout", response_model=FunnelCheckoutRead)
async def create_public_checkout_session(
    product_id: UUID,
    payload: FunnelCheckoutCreatePublic,
    service: FunnelCheckoutService = Depends(get_checkout_service),
):
    """Create a Stripe checkout session for a public buyer (tenant isolated)."""
    result = await service.create_checkout_session(
        organization_id=payload.organization_id,
        product_id=product_id,
        payload=payload,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Product not found or not published")
    return result
