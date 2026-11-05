from datetime import UTC, datetime
from typing import Annotated, TypedDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.database import get_db
from app.models.contact import Contact
from app.models.content_draft import ContentDraft
from app.models.opportunity import Opportunity
from app.models.submission import Submission
from app.models.user import User
from app.schemas.draft import DraftList, DraftOut

router = APIRouter(prefix="/drafts", tags=["drafts"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
DraftStatus = Annotated[str, Query()]


class DraftStatusResponse(TypedDict):
    status: str


class RejectDraftPayload(BaseModel):
    reason: str = ""


def _admin_organization_id(admin: User) -> UUID:
    if admin.organization_id is None:
        raise HTTPException(status_code=403, detail="Organization required")
    return admin.organization_id


def _draft_tenant_scope(organization_id: UUID) -> tuple:
    return (
        or_(
            ContentDraft.opportunity_id.is_not(None),
            ContentDraft.contact_id.is_not(None),
            ContentDraft.submission_id.is_not(None),
        ),
        or_(
            ContentDraft.opportunity_id.is_(None),
            ContentDraft.opportunity_id.in_(
                select(Opportunity.id).where(
                    Opportunity.organization_id == organization_id
                )
            ),
        ),
        or_(
            ContentDraft.contact_id.is_(None),
            ContentDraft.contact_id.in_(
                select(Contact.id).where(
                    Contact.organization_id == organization_id
                )
            ),
        ),
        or_(
            ContentDraft.submission_id.is_(None),
            ContentDraft.submission_id.in_(
                select(Submission.id).where(
                    Submission.organization_id == organization_id
                )
            ),
        ),
    )


async def _get_scoped_draft(
    db: AsyncSession, draft_id: UUID, organization_id: UUID
) -> ContentDraft | None:
    return await db.scalar(
        select(ContentDraft).where(
            ContentDraft.id == draft_id,
            *_draft_tenant_scope(organization_id),
        )
    )


@router.get("", response_model=DraftList)
async def list_drafts(
    db: DbSession,
    admin: User = Depends(require_admin),
    status: DraftStatus = "pending",
) -> DraftList:
    organization_id = _admin_organization_id(admin)
    query = select(ContentDraft).where(*_draft_tenant_scope(organization_id))
    if status:
        query = query.where(ContentDraft.status == status)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(query.order_by(desc(ContentDraft.created_at)))
    items = [DraftOut.model_validate(item) for item in result.scalars().all()]
    return DraftList(total=int(total or 0), items=items)


@router.get("/{draft_id}", response_model=DraftOut)
async def get_draft(
    draft_id: UUID,
    db: DbSession,
    admin: User = Depends(require_admin),
) -> DraftOut:
    organization_id = _admin_organization_id(admin)
    row = await _get_scoped_draft(db, draft_id, organization_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return DraftOut.model_validate(row)


@router.patch("/{draft_id}/approve")
async def approve_draft(
    draft_id: UUID,
    db: DbSession,
    admin: User = Depends(require_admin),
) -> DraftStatusResponse:
    organization_id = _admin_organization_id(admin)
    row = await _get_scoped_draft(db, draft_id, organization_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    row.status = "approved"
    row.approved_at = datetime.now(UTC)
    await db.commit()
    return {"status": row.status or "approved"}


@router.patch("/{draft_id}/reject")
async def reject_draft(
    draft_id: UUID,
    payload: RejectDraftPayload,
    db: DbSession,
    admin: User = Depends(require_admin),
) -> DraftStatusResponse:
    organization_id = _admin_organization_id(admin)
    row = await _get_scoped_draft(db, draft_id, organization_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    row.status = "rejected"
    row.rejection_reason = payload.reason
    row.updated_at = datetime.now(UTC)
    await db.commit()
    return {"status": row.status or "rejected"}
