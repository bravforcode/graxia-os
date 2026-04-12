from datetime import datetime, timezone
from typing import Annotated, TypedDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.opportunity import Opportunity
from app.schemas.opportunity import OpportunityList, OpportunityOut

router = APIRouter(prefix="/opportunities", tags=["opportunities"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
StatusFilter = Annotated[str | None, Query()]
DecisionFilter = Annotated[str | None, Query()]
ActionPriorityFilter = Annotated[str | None, Query()]
ResultLimit = Annotated[int, Query(ge=1, le=100)]
ResultOffset = Annotated[int, Query(ge=0)]


class StatusIdResponse(TypedDict):
    status: str
    id: str


def _active_opportunities():
    return select(Opportunity).where(Opportunity.is_deleted.is_(False))


@router.get("", response_model=OpportunityList)
async def list_opportunities(
    db: DbSession,
    status: StatusFilter = None,
    decision: DecisionFilter = None,
    action_priority: ActionPriorityFilter = None,
    limit: ResultLimit = 20,
    offset: ResultOffset = 0,
) -> OpportunityList:
    query = _active_opportunities()
    if status:
        query = query.where(Opportunity.status == status)
    if decision:
        query = query.where(Opportunity.decision == decision)
    if action_priority:
        query = query.where(Opportunity.action_priority == action_priority)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(desc(Opportunity.total_score), desc(Opportunity.found_at))
        .offset(offset)
        .limit(limit)
    )
    items = [OpportunityOut.model_validate(item) for item in result.scalars().all()]
    return OpportunityList(total=int(total or 0), items=items)


@router.get("/high-score", response_model=OpportunityList)
async def get_high_score_opportunities(
    db: DbSession,
    threshold: float = 7.0,
    limit: ResultLimit = 10,
) -> OpportunityList:
    result = await db.execute(
        _active_opportunities()
        .where(Opportunity.total_score >= threshold)
        .order_by(desc(Opportunity.total_score), desc(Opportunity.found_at))
        .limit(limit)
    )
    items = [OpportunityOut.model_validate(item) for item in result.scalars().all()]
    return OpportunityList(total=len(items), items=items)


@router.get("/{opp_id}", response_model=OpportunityOut)
async def get_opportunity(opp_id: UUID, db: DbSession) -> OpportunityOut:
    row = (
        await db.execute(_active_opportunities().where(Opportunity.id == opp_id).limit(1))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return OpportunityOut.model_validate(row)


@router.patch("/{opp_id}/approve")
async def approve_opportunity(opp_id: UUID, db: DbSession) -> StatusIdResponse:
    row = (
        await db.execute(_active_opportunities().where(Opportunity.id == opp_id).limit(1))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    row.status = "approved"
    row.decision = row.decision or "do_now"
    row.action_priority = "do_now"
    row.acted_on_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": row.status or "approved", "id": str(row.id)}


@router.patch("/{opp_id}/skip")
async def skip_opportunity(opp_id: UUID, db: DbSession) -> StatusIdResponse:
    row = (
        await db.execute(_active_opportunities().where(Opportunity.id == opp_id).limit(1))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    row.status = "ignored"
    row.decision = "skip"
    row.action_priority = "skip"
    row.acted_on_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": row.status, "id": str(row.id)}
