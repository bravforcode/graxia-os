from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.job_posting import JobPosting
from app.schemas.job import JobPostingList, JobPostingOut, JobStatusUpdate

router = APIRouter(prefix="/jobs", tags=["jobs"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
StatusFilter = Annotated[str | None, Query()]
PlatformFilter = Annotated[str | None, Query()]
JobTypeFilter = Annotated[str | None, Query()]
MinScoreFilter = Annotated[float | None, Query(ge=0, le=10)]
ResultLimit = Annotated[int, Query(ge=1, le=100)]
ResultOffset = Annotated[int, Query(ge=0)]


@router.get("", response_model=JobPostingList)
async def list_jobs(
    db: DbSession,
    status: StatusFilter = None,
    source_platform: PlatformFilter = None,
    job_type: JobTypeFilter = None,
    min_score: MinScoreFilter = None,
    limit: ResultLimit = 20,
    offset: ResultOffset = 0,
) -> JobPostingList:
    query = select(JobPosting)
    if status:
        query = query.where(JobPosting.status == status)
    if source_platform:
        query = query.where(JobPosting.source_platform == source_platform)
    if job_type:
        query = query.where(JobPosting.job_type == job_type)
    if min_score is not None:
        query = query.where(JobPosting.match_score >= min_score)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(desc(JobPosting.match_score), desc(JobPosting.created_at))
        .offset(offset)
        .limit(limit)
    )
    items = [JobPostingOut.model_validate(item) for item in result.scalars().all()]
    return JobPostingList(total=int(total or 0), items=items)


@router.get("/stats")
async def get_job_stats(db: DbSession) -> dict[str, object]:
    rows = (
        await db.execute(select(JobPosting.status, func.count(JobPosting.id)).group_by(JobPosting.status))
    ).all()
    total_jobs = int(sum(int(count) for _, count in rows))
    average_score = await db.scalar(select(func.avg(JobPosting.match_score)))
    return {
        "total_jobs": total_jobs,
        "by_status": {status or "unknown": int(count) for status, count in rows},
        "average_score": float(average_score or 0),
    }


@router.get("/{job_id}", response_model=JobPostingOut)
async def get_job(job_id: UUID, db: DbSession) -> JobPostingOut:
    row = await db.get(JobPosting, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job posting not found")
    return JobPostingOut.model_validate(row)


@router.patch("/{job_id}/status", response_model=JobPostingOut)
async def patch_job_status(job_id: UUID, payload: JobStatusUpdate, db: DbSession) -> JobPostingOut:
    row = await db.get(JobPosting, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job posting not found")
    row.status = payload.status
    row.follow_up_due = payload.follow_up_due
    await db.commit()
    await db.refresh(row)
    return JobPostingOut.model_validate(row)
