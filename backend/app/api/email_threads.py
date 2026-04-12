from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.email_message import EmailMessage
from app.models.email_thread import EmailThread

router = APIRouter(prefix="/api/v1/email-threads", tags=["email"])


class EmailThreadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    thread_id: str
    subject: Optional[str]
    participants: list
    category: Optional[str]
    priority: int
    last_message_at: Optional[datetime]
    unread_count: int
    has_attachments: bool
    action_items: list
    status: str
    created_at: datetime
    updated_at: datetime

class EmailMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    thread_id: UUID
    message_id: str
    from_email: str
    to_email: str
    subject: str
    body: str
    received_at: datetime
    is_read: bool
    created_at: datetime

class EmailThreadListResponse(BaseModel):
    total: int
    items: list[EmailThreadResponse]


class EmailStatsResponse(BaseModel):
    total_threads: int
    unread_count: int
    action_items_count: int
    by_category: dict[str, int]


@router.get("/stats", response_model=EmailStatsResponse)
@router.get("/stats/summary", response_model=EmailStatsResponse)
async def get_email_stats(db: AsyncSession = Depends(get_db)):
    category_rows = (
        await db.execute(select(EmailThread.category, func.count(EmailThread.id)).group_by(EmailThread.category))
    ).all()
    total_threads = await db.scalar(select(func.count(EmailThread.id)))
    unread_count = await db.scalar(select(func.count(EmailThread.id)).where(EmailThread.unread_count > 0))

    action_items_count = 0
    thread_rows = (await db.execute(select(EmailThread.action_items))).scalars().all()
    for items in thread_rows:
        action_items_count += len(items or [])

    return EmailStatsResponse(
        total_threads=int(total_threads or 0),
        unread_count=int(unread_count or 0),
        action_items_count=action_items_count,
        by_category={category or "uncategorized": int(count) for category, count in category_rows},
    )


@router.get("/", response_model=EmailThreadListResponse)
async def list_email_threads(
    db: AsyncSession = Depends(get_db),
    category: Optional[str] = Query(None, description="Filter by category"),
    status: Optional[str] = Query(None, description="Filter by status"),
    unread_only: bool = Query(False, description="Show only unread"),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
):
    query = select(EmailThread)
    if category:
        query = query.where(EmailThread.category == category)
    if status:
        query = query.where(EmailThread.status == status)
    if unread_only:
        query = query.where(EmailThread.unread_count > 0)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(desc(EmailThread.priority), desc(EmailThread.last_message_at))
        .offset(offset)
        .limit(limit)
    )
    items = [EmailThreadResponse.model_validate(thread) for thread in result.scalars().all()]
    return EmailThreadListResponse(total=int(total or 0), items=items)


@router.get("/{thread_id}", response_model=EmailThreadResponse)
async def get_email_thread(thread_id: UUID, db: AsyncSession = Depends(get_db)):
    query = select(EmailThread).where(EmailThread.id == thread_id)
    result = await db.execute(query)
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Email thread not found")
    return EmailThreadResponse.model_validate(thread)


@router.get("/{thread_id}/messages", response_model=list[EmailMessageResponse])
async def get_thread_messages(thread_id: UUID, db: AsyncSession = Depends(get_db)):
    query = (
        select(EmailMessage)
        .where(EmailMessage.thread_id == thread_id)
        .order_by(EmailMessage.received_at.asc())
    )
    result = await db.execute(query)
    messages = result.scalars().all()
    return [EmailMessageResponse.model_validate(msg) for msg in messages]


@router.patch("/{thread_id}/mark-read", response_model=EmailThreadResponse)
@router.post("/{thread_id}/mark-read", response_model=EmailThreadResponse)
async def mark_thread_read(thread_id: UUID, db: AsyncSession = Depends(get_db)):
    query = select(EmailThread).where(EmailThread.id == thread_id)
    result = await db.execute(query)
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(status_code=404, detail="Email thread not found")

    thread.mark_as_read()
    thread.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(thread)
    return EmailThreadResponse.model_validate(thread)
