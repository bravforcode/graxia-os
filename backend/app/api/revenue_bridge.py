from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.revenue_bridge import (
    RevenueBridgeEventEnvelope,
    RevenueBridgeIngestResponse,
)
from app.services.revenue_bridge_service import (
    InvalidRevenueBridgeSignature,
    RevenueBridgeDisabled,
    RevenueBridgeConflictError,
    RevenueBridgeService,
)

router = APIRouter(prefix="/revenue-bridge", tags=["revenue-bridge"])


@router.post(
    "/events",
    response_model=RevenueBridgeIngestResponse,
    status_code=status.HTTP_200_OK,
)
async def ingest_revenue_event(
    envelope: RevenueBridgeEventEnvelope,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Accept verified provider evidence; activation is never client-driven."""

    try:
        return await RevenueBridgeService().ingest(envelope, db)
    except InvalidRevenueBridgeSignature as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        ) from exc
    except RevenueBridgeConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider event ID conflict",
        ) from exc
    except RevenueBridgeDisabled as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Revenue bridge is temporarily disabled",
        ) from exc
