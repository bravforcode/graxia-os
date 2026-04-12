from datetime import datetime, timezone
from typing import Annotated, TypedDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.content_draft import ContentDraft
from app.schemas.draft import DraftList, DraftOut

router = APIRouter(prefix="/drafts", tags=["drafts"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
DraftStatus = Annotated[str, Query()]


class DraftStatusResponse(TypedDict):
    status: str


class RejectDraftPayload(BaseModel):
    reason: str = ""


@router.get("", response_model=DraftList)
async def list_drafts(db: DbSession, status: DraftStatus = "pending") -> DraftList:
    query = select(ContentDraft)
    if status:
        query = query.where(ContentDraft.status == status)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(query.order_by(desc(ContentDraft.created_at)))
    items = [DraftOut.model_validate(item) for item in result.scalars().all()]
    return DraftList(total=int(total or 0), items=items)


@router.get("/{draft_id}", response_model=DraftOut)
async def get_draft(draft_id: UUID, db: DbSession) -> DraftOut:
    row = await db.get(ContentDraft, draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return DraftOut.model_validate(row)


@router.patch("/{draft_id}/approve")
async def approve_draft(draft_id: UUID, db: DbSession) -> DraftStatusResponse:
    row = await db.get(ContentDraft, draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    row.status = "approved"
    row.approved_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": row.status or "approved"}


@router.patch("/{draft_id}/reject")
async def reject_draft(
    draft_id: UUID,
    payload: RejectDraftPayload,
    db: DbSession,
) -> DraftStatusResponse:
    row = await db.get(ContentDraft, draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    row.status = "rejected"
    row.rejection_reason = payload.reason
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": row.status or "rejected"}
