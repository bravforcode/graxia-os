from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.database import get_db
from app.models.submission import Submission
from app.schemas.submission import SubmissionOut, SubmissionCreate

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.get("", response_model=list[SubmissionOut])
async def list_submissions(status: str = None, db: AsyncSession = Depends(get_db)):
    q = select(Submission).order_by(desc(Submission.created_at))
    if status:
        q = q.where(Submission.status == status)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=SubmissionOut, status_code=201)
async def create_submission(data: SubmissionCreate, db: AsyncSession = Depends(get_db)):
    sub = Submission(**data.model_dump())
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


@router.patch("/{sub_id}/mark-won")
async def mark_won(sub_id: UUID, actual_value: float = 0, db: AsyncSession = Depends(get_db)):
    sub = await db.get(Submission, sub_id)
    if not sub:
        raise HTTPException(404, "Not found")
    sub.status = "won"
    sub.actual_value = actual_value
    await db.commit()
    from app.core.event_bus import event_bus
    await event_bus.emit("submission.won", {"submission_id": str(sub_id), "actual_value_thb": actual_value})
    return {"status": "won"}


@router.patch("/{sub_id}/mark-lost")
async def mark_lost(sub_id: UUID, lost_reason: str = "unknown", db: AsyncSession = Depends(get_db)):
    sub = await db.get(Submission, sub_id)
    if not sub:
        raise HTTPException(404, "Not found")
    sub.status = "lost"
    sub.lost_reason_primary = lost_reason
    await db.commit()
    from app.core.event_bus import event_bus
    await event_bus.emit("submission.lost", {"submission_id": str(sub_id), "lost_reason": lost_reason})
    return {"status": "lost"}
