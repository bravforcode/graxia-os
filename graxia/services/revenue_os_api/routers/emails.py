"""
graxia/services/revenue_os_api/routers/emails.py
Email outbox management.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.models import EmailOutbox, EmailStatus
from ....packages.revenue_os.schemas import EmailResponse
from ..dependencies import require_admin_api_key

router = APIRouter()


@router.get(
    "/",
    response_model=list[EmailResponse],
    dependencies=[Depends(require_admin_api_key)],
)
async def list_emails(
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[EmailResponse]:
    stmt = select(EmailOutbox)
    if status_filter:
        stmt = stmt.where(EmailOutbox.status == status_filter)
    result = await db.scalars(
        stmt.order_by(EmailOutbox.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [EmailResponse.model_validate(e) for e in result]


@router.post(
    "/{email_id}/cancel",
    response_model=EmailResponse,
    dependencies=[Depends(require_admin_api_key)],
    summary="Cancel a pending email before it is sent",
)
async def cancel_email(
    email_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> EmailResponse:
    email = await db.get(EmailOutbox, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    if email.status != EmailStatus.PENDING.value:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel email with status '{email.status}'",
        )
    email.status = EmailStatus.CANCELLED.value
    await db.flush()
    return EmailResponse.model_validate(email)


@router.post(
    "/{email_id}/retry",
    response_model=EmailResponse,
    dependencies=[Depends(require_admin_api_key)],
    summary="Reset a failed email to pending for retry",
)
async def retry_email(
    email_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> EmailResponse:
    email = await db.get(EmailOutbox, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    if email.status not in (EmailStatus.FAILED.value, EmailStatus.CANCELLED.value):
        raise HTTPException(
            status_code=409,
            detail=f"Can only retry failed/cancelled emails, not '{email.status}'",
        )
    email.status = EmailStatus.PENDING.value
    email.retry_count = 0
    email.last_error = None
    await db.flush()
    return EmailResponse.model_validate(email)
