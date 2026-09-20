import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.middleware.tenant import get_org
from app.models.organization import Organization
from app.schemas.funnel import (
    LeadMagnetCreate,
    LeadMagnetUpdate,
    LeadMagnetRead,
    LeadCaptureRequest,
    LeadCaptureResponse,
    UnsubscribeRequest,
    UnsubscribeResponse,
)
from app.services.lead_magnet_service import LeadMagnetService
from app.services.public_funnel_service import (
    PublicFunnelBindingError,
    require_public_funnel_organization,
)

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
        organization_id = require_public_funnel_organization(payload.organization_id)
        contact, raw_token = await service.capture_lead(
            organization_id=organization_id,
            slug=slug,
            email=payload.email,
            name=payload.name,
            source=payload.source,
            medium=payload.medium,
            campaign=payload.campaign,
            referrer=payload.referrer,
            marketing_consent=payload.marketing_consent,
            consent_version=payload.consent_version,
            session_id=payload.session_id,
            public=True,
        )
        
        delivery_url = None
        if raw_token:
            delivery_url = f"/delivery/{raw_token}"

        if payload.marketing_consent:
            broker = getattr(settings, "CELERY_BROKER_URL", "") or getattr(settings, "REDIS_URL", "")
            if broker:
                from app.tasks.funnel_automation_tasks import send_lead_nurture

                send_lead_nurture.apply_async(
                    args=[str(organization_id), str(contact.id)],
                    task_id=f"lead-nurture:{contact.id}",
                )
            else:
                logger.info("Lead nurture suppressed: no task broker configured")
            
        return LeadCaptureResponse(
            contact_id=contact.id,
            raw_token=raw_token,
            delivery_url=delivery_url,
        )
    except PublicFunnelBindingError as e:
        return JSONResponse(
            status_code=503 if "not configured" in str(e) else 404,
            content={"detail": str(e)},
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(e)},
        )


@router.post("/public/funnel/unsubscribe", response_model=UnsubscribeResponse)
async def unsubscribe_from_marketing(
    payload: UnsubscribeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Suppress future marketing sends; response does not reveal contact existence."""
    try:
        organization_id = require_public_funnel_organization(payload.organization_id)
    except PublicFunnelBindingError as exc:
        raise HTTPException(
            status_code=503 if "not configured" in str(exc) else 404,
            detail=str(exc),
        ) from exc
    await LeadMagnetService(db).unsubscribe(organization_id, payload.email, public=True)
    return UnsubscribeResponse(ok=True)
