import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.tenant import get_org
from app.models.organization import Organization
from app.schemas.funnel import (
    LeadMagnetCreate,
    LeadMagnetUpdate,
    LeadMagnetRead,
    LeadCaptureRequest,
    LeadCaptureResponse,
)
from app.services.lead_magnet_service import LeadMagnetService

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Admin Endpoints ───────────────────────────────────────────────────────

@router.post("/funnel/lead-magnets", response_model=LeadMagnetRead, status_code=status.HTTP_201_CREATED)
async def create_lead_magnet(
    payload: LeadMagnetCreate,
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    service = LeadMagnetService(db)
    return await service.create_lead_magnet(organization_id=org.id, payload=payload)

@router.get("/funnel/lead-magnets", response_model=List[LeadMagnetRead])
async def list_lead_magnets(
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    service = LeadMagnetService(db)
    return await service.list_lead_magnets(organization_id=org.id)

@router.get("/funnel/lead-magnets/{lm_id}", response_model=LeadMagnetRead)
async def get_lead_magnet(
    lm_id: UUID,
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    service = LeadMagnetService(db)
    lm = await service.get_lead_magnet(organization_id=org.id, lead_magnet_id=lm_id)
    if not lm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead magnet not found",
        )
    return lm

@router.put("/funnel/lead-magnets/{lm_id}", response_model=LeadMagnetRead)
async def update_lead_magnet(
    lm_id: UUID,
    payload: LeadMagnetUpdate,
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    service = LeadMagnetService(db)
    lm = await service.update_lead_magnet(organization_id=org.id, lead_magnet_id=lm_id, payload=payload)
    if not lm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead magnet not found",
        )
    return lm

@router.delete("/funnel/lead-magnets/{lm_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead_magnet(
    lm_id: UUID,
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    service = LeadMagnetService(db)
    success = await service.delete_lead_magnet(organization_id=org.id, lead_magnet_id=lm_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead magnet not found",
        )

# ── Public Endpoints ──────────────────────────────────────────────────────

@router.post("/public/funnel/lead-magnets/{slug}/capture", response_model=LeadCaptureResponse, status_code=status.HTTP_201_CREATED)
async def capture_lead(
    slug: str,
    payload: LeadCaptureRequest,
    db: AsyncSession = Depends(get_db),
):
    service = LeadMagnetService(db)
    try:
        contact, raw_token = await service.capture_lead(
            organization_id=payload.organization_id,
            slug=slug,
            email=payload.email,
            name=payload.name,
            source=payload.source,
            medium=payload.medium,
            campaign=payload.campaign,
            referrer=payload.referrer,
        )
        
        delivery_url = None
        if raw_token:
            delivery_url = f"/delivery/{raw_token}"
            
        return LeadCaptureResponse(
            contact_id=contact.id,
            raw_token=raw_token,
            delivery_url=delivery_url,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
