from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import asc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.career import bootstrap_skill_profiles, ensure_skill_profiles_seeded
from app.database import get_db
from app.models.skill_profile import SkillProfile
from app.schemas.skill import SkillBootstrapResponse, SkillProfileList, SkillProfileOut

router = APIRouter(prefix="/skills", tags=["skills"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CategoryFilter = Annotated[str | None, Query()]
ActiveOnlyFilter = Annotated[bool | None, Query()]
ResultLimit = Annotated[int, Query(ge=1, le=200)]
ResultOffset = Annotated[int, Query(ge=0)]


@router.get("", response_model=SkillProfileList)
async def list_skills(
    db: DbSession,
    category: CategoryFilter = None,
    active_only: ActiveOnlyFilter = True,
    limit: ResultLimit = 50,
    offset: ResultOffset = 0,
) -> SkillProfileList:
    await ensure_skill_profiles_seeded()

    query = select(SkillProfile)
    if category:
        query = query.where(SkillProfile.category == category)
    if active_only is not None:
        query = query.where(SkillProfile.is_active.is_(active_only))

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(asc(SkillProfile.category), asc(SkillProfile.name))
        .offset(offset)
        .limit(limit)
    )
    items = [SkillProfileOut.model_validate(item) for item in result.scalars().all()]
    return SkillProfileList(total=int(total or 0), items=items)


@router.post("/bootstrap", response_model=SkillBootstrapResponse)
async def bootstrap_skills(force: bool = False) -> SkillBootstrapResponse:
    result = await bootstrap_skill_profiles(force=force)
    return SkillBootstrapResponse(**result)
