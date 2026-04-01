from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.database import get_db
from app.models.content_draft import ContentDraft
from app.schemas.draft import DraftOut, DraftList

router = APIRouter(prefix="/drafts", tags=["drafts"])


@router.get("", response_model=DraftList)
async def list_drafts(status: str = "pending", db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func
    q = select(ContentDraft).where(ContentDraft.status == status).order_by(desc(ContentDraft.created_at))
    total = await db.scalar(select(func.count()).select_from(select(ContentDraft).where(ContentDraft.status == status).subquery()))
    result = await db.execute(q)
    return DraftList(total=total or 0, items=result.scalars().all())


@router.get("/{draft_id}", response_model=DraftOut)
async def get_draft(draft_id: UUID, db: AsyncSession = Depends(get_db)):
    d = await db.get(ContentDraft, draft_id)
    if not d:
        raise HTTPException(404, "Draft not found")
    return d


@router.patch("/{draft_id}/approve")
async def approve_draft(draft_id: UUID, db: AsyncSession = Depends(get_db)):
    from datetime import datetime, timezone
    d = await db.get(ContentDraft, draft_id)
    if not d:
        raise HTTPException(404, "Not found")
    d.status = "approved"
    d.approved_at = datetime.now(timezone.utc)
    await db.commit()
    from app.core.event_bus import event_bus
    await event_bus.emit("draft.approved", {"draft_id": str(draft_id), "draft_type": d.type})
    return {"status": "approved"}


@router.patch("/{draft_id}/reject")
async def reject_draft(draft_id: UUID, reason: str = "", db: AsyncSession = Depends(get_db)):
    d = await db.get(ContentDraft, draft_id)
    if not d:
        raise HTTPException(404, "Not found")
    d.status = "rejected"
    d.rejection_reason = reason
    await db.commit()
    return {"status": "rejected"}
