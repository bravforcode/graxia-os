from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.automation_run import AutomationRun
from app.models.user import User
from app.schemas.run import AutomationRunList, AutomationRunOut

router = APIRouter(prefix="/runs", tags=["runs"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user_from_token)]
RunStatus = Annotated[str | None, Query()]
ResultLimit = Annotated[int, Query(ge=1, le=100)]
ResultOffset = Annotated[int, Query(ge=0)]


@router.get("", response_model=AutomationRunList)
async def list_runs(
    db: DbSession,
    current_user: CurrentUser,
    status: RunStatus = None,
    limit: ResultLimit = 20,
    offset: ResultOffset = 0,
) -> AutomationRunList:
    query = select(AutomationRun).where(
        AutomationRun.organization_id == current_user.organization_id
    )
    if status:
        query = query.where(AutomationRun.status == status)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(desc(AutomationRun.queued_at)).offset(offset).limit(limit)
    )
    items = [AutomationRunOut.model_validate(item) for item in result.scalars().all()]
    return AutomationRunList(total=int(total or 0), items=items)


@router.get("/{run_id}", response_model=AutomationRunOut)
async def get_run(
    run_id: UUID, db: DbSession, current_user: CurrentUser
) -> AutomationRunOut:
    result = await db.execute(
        select(AutomationRun).where(
            AutomationRun.id == run_id,
            AutomationRun.organization_id == current_user.organization_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return AutomationRunOut.model_validate(run)
