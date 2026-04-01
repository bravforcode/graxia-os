from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.database import get_db
from app.models.opportunity import Opportunity
from app.schemas.opportunity import OpportunityOut, OpportunityList

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.get("", response_model=OpportunityList)
async def list_opportunities(
    status: str = None,
    decision: str = None,
    action_priority: str = None,
    limit: int = Query(20, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    q = select(Opportunity)
    if status:
        q = q.where(Opportunity.status == status)
    if decision:
        q = q.where(Opportunity.decision == decision)
    if action_priority:
        q = q.where(Opportunity.action_priority == action_priority)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    q = q.order_by(desc(Opportunity.total_score)).offset(offset).limit(limit)
    result = await db.execute(q)
    items = result.scalars().all()
    return OpportunityList(total=total or 0, items=items)


@router.get("/{opp_id}", response_model=OpportunityOut)
async def get_opportunity(opp_id: UUID, db: AsyncSession = Depends(get_db)):
    opp = await db.get(Opportunity, opp_id)
    if not opp:
        raise HTTPException(404, "Opportunity not found")
    return opp


@router.patch("/{opp_id}/approve")
async def approve_opportunity(opp_id: UUID, db: AsyncSession = Depends(get_db)):
    opp = await db.get(Opportunity, opp_id)
    if not opp:
        raise HTTPException(404, "Not found")
    opp.status = "approved"
    await db.commit()
    return {"status": "approved", "id": str(opp_id)}


@router.patch("/{opp_id}/skip")
async def skip_opportunity(opp_id: UUID, db: AsyncSession = Depends(get_db)):
    opp = await db.get(Opportunity, opp_id)
    if not opp:
        raise HTTPException(404, "Not found")
    opp.status = "ignored"
    opp.decision = "skip"
    await db.commit()
    return {"status": "ignored", "id": str(opp_id)}
