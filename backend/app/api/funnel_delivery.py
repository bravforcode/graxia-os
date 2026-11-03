import logging
import mimetypes
from typing import List
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.database import get_db
from app.models.funnel import DeliveryAccess
from app.models.user import User
from app.services.funnel_delivery_service import FunnelDeliveryService
from app.schemas.funnel import (
    DeliveryAccessGrantResponse,
    DeliveryMetadata,
    DeliveryPayload,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _admin_organization_id(admin: User) -> UUID:
    if admin.organization_id is None:
        raise HTTPException(status_code=403, detail="Organization required")
    return admin.organization_id


def _add_file_download_url(payload: dict, token: str) -> dict:
    if payload.get("asset_type") == "file":
        payload["download_url"] = (
            f"/api/v1/funnel/delivery/{quote(token, safe='')}/download"
        )
    return payload


@router.post("/orders/{order_id}/grant-delivery", response_model=List[DeliveryAccessGrantResponse], status_code=status.HTTP_201_CREATED)
async def grant_delivery(
    order_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Grant delivery access for all products in a paid order (Admin only)."""
    organization_id = _admin_organization_id(admin)
    service = FunnelDeliveryService(db)
    results = await service.grant_delivery_access_for_order(
        organization_id, order_id
    )
    return [
        DeliveryAccessGrantResponse(access_id=access.id, raw_token=raw_token)
        for access, raw_token in results
    ]

@router.get(
    "/delivery/{token}",
    response_model=DeliveryMetadata,
    response_model_exclude_none=True,
)
async def get_delivery(
    token: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Open a delivery page without consuming a download."""
    response.headers["Cache-Control"] = "private, no-store"
    service = FunnelDeliveryService(db)
    access = await service.get_delivery_access_by_token(token)
    if not access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired delivery token"
        )
    metadata = await service.get_delivery_metadata(access)
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset details not found"
        )
    await service.record_open(access)
    return _add_file_download_url(metadata, token)

@router.post(
    "/delivery/{token}/consume",
    response_model=DeliveryPayload,
    response_model_exclude_none=True,
)
async def consume_delivery(
    token: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Explicitly consume one delivery use and return the safe payload."""
    response.headers["Cache-Control"] = "private, no-store"
    service = FunnelDeliveryService(db)
    access = await service.get_delivery_access_by_token(token)
    if not access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired delivery token"
        )
    metadata = await service.get_delivery_metadata(access)
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset details not found"
        )
    if metadata["asset_type"] == "file":
        return _add_file_download_url(metadata, token)

    payload = await service.get_delivery_payload(access)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset details not found"
        )
    access = await service.consume_delivery_access(access)
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
    return _add_file_download_url(payload, token)

@router.get("/delivery/{token}/download")
async def download_delivery(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Stream a safe file attachment; never expose its storage path."""
    service = FunnelDeliveryService(db)
    download = await service.get_file_download(token)
    if not download:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or unavailable delivery",
        )
    path, filename = download
    return FileResponse(
        path=path,
        media_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
        filename=filename,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )

@router.post("/events/delivery-opened", response_model=dict)
async def track_delivery_opened(
    access_token: str,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint to track that a delivery was opened, by raw token."""
    service = FunnelDeliveryService(db)
    access = await service.get_delivery_access_by_token(access_token)
    if not access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired delivery token",
        )
    access = await service.record_open(access)
    return {"status": "tracked", "access_id": str(access.id)}


@router.post("/delivery-access/{access_id}/revoke", status_code=status.HTTP_200_OK)
async def revoke_delivery_access(
    access_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a delivery access token (Admin only)."""
    organization_id = _admin_organization_id(admin)
    stmt = select(DeliveryAccess).where(
        and_(
            DeliveryAccess.id == access_id,
            DeliveryAccess.organization_id == organization_id
        )
    )
    res = await db.execute(stmt)
    access = res.scalar_one_or_none()
    if not access:
        raise HTTPException(status_code=404, detail="Delivery access not found")
    
    access.status = "revoked"
    await db.commit()
    return {"status": "revoked"}
