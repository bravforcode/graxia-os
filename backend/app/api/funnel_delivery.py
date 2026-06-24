import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.tenant import get_org
from app.models.organization import Organization
from app.models.funnel import DeliveryAccess
from app.services.funnel_delivery_service import FunnelDeliveryService
from app.schemas.funnel import (
    DeliveryAccessGrantResponse,
    DeliveryPayload,
)

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/orders/{order_id}/grant-delivery", response_model=List[DeliveryAccessGrantResponse], status_code=status.HTTP_201_CREATED)
async def grant_delivery(
    order_id: UUID,
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    """Grant delivery access for all products in a paid order (Admin only)."""
    service = FunnelDeliveryService(db)
    results = await service.grant_delivery_access_for_order(org.id, order_id)
    return [
        DeliveryAccessGrantResponse(access_id=access.id, raw_token=raw_token)
        for access, raw_token in results
    ]

@router.get("/delivery/{token}", response_model=DeliveryPayload)
async def get_delivery(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint to retrieve and consume a delivery asset via raw token."""
    service = FunnelDeliveryService(db)
    access = await service.get_delivery_access_by_token(token)
    if not access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired delivery token"
        )
    payload = await service.get_delivery_payload(access)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset details not found"
        )
    return payload

@router.post("/delivery/{token}/consume", response_model=DeliveryPayload)
async def consume_delivery(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint to explicitly consume a token and return the payload."""
    service = FunnelDeliveryService(db)
    access = await service.get_delivery_access_by_token(token)
    if not access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired delivery token"
        )
    payload = await service.get_delivery_payload(access)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset details not found"
        )
    return payload

@router.post("/delivery-access/{access_id}/revoke", status_code=status.HTTP_200_OK)
async def revoke_delivery_access(
    access_id: UUID,
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a delivery access token (Admin only)."""
    stmt = select(DeliveryAccess).where(
        and_(
            DeliveryAccess.id == access_id,
            DeliveryAccess.organization_id == org.id
        )
    )
    res = await db.execute(stmt)
    access = res.scalar_one_or_none()
    if not access:
        raise HTTPException(status_code=404, detail="Delivery access not found")
    
    access.status = "revoked"
    await db.commit()
    return {"status": "revoked"}
