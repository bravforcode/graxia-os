"""
graxia/services/revenue_os_api/routers/incidents.py
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.models import IncidentEvent
from ....packages.revenue_os.schemas import IncidentCreateRequest, IncidentResponse
from ..dependencies import require_admin_api_key

router = APIRouter()


@router.get("/", response_model=list[IncidentResponse], dependencies=[Depends(require_admin_api_key)])
async def list_incidents(
    open_only: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[IncidentResponse]:
    stmt = select(IncidentEvent)
    if open_only:
        stmt = stmt.where(IncidentEvent.resolved_at.is_(None))
    result = await db.scalars(stmt.order_by(IncidentEvent.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return [IncidentResponse.model_validate(i) for i in result]


@router.post("/", response_model=IncidentResponse, status_code=201, dependencies=[Depends(require_admin_api_key)])
async def create_incident(payload: IncidentCreateRequest, db: AsyncSession = Depends(get_db)) -> IncidentResponse:
    incident = IncidentEvent(**payload.model_dump())
    db.add(incident)
    await db.flush()
    return IncidentResponse.model_validate(incident)


@router.post("/{incident_id}/resolve", response_model=IncidentResponse, dependencies=[Depends(require_admin_api_key)])
async def resolve_incident(
    incident_id: UUID,
    resolution_notes: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
) -> IncidentResponse:
    incident = await db.get(IncidentEvent, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident.resolved_at = datetime.utcnow()
    incident.resolution_notes = resolution_notes
    await db.flush()
    return IncidentResponse.model_validate(incident)
