from datetime import date, datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import event_bus
from app.database import get_db
from app.models.contact import Contact
from app.schemas.contact import ContactCreate, ContactOut, ContactUpdate

router = APIRouter(prefix="/contacts", tags=["contacts"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class ContactList(BaseModel):
    total: int
    items: list[ContactOut]


class ContactBulkResult(BaseModel):
    created: int
    updated: int
    items: list[ContactOut]


class ContactStats(BaseModel):
    total: int
    leads: int
    with_email: int
    followup_due: int
    by_type: dict[str, int]


class ContactListFilters(BaseModel):
    q: str | None = None
    contact_type: str | None = None
    min_value_score: int | None = Field(default=None, ge=1, le=10)
    followup_due_only: bool = False
    limit: int = Field(default=100, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


def _active_contacts():
    return select(Contact).where(Contact.is_deleted.is_(False))


@router.get("", response_model=ContactList)
async def list_contacts(
    db: DbSession,
    q: Annotated[str | None, Query(max_length=120)] = None,
    contact_type: Annotated[str | None, Query(max_length=50)] = None,
    min_value_score: Annotated[int | None, Query(ge=1, le=10)] = None,
    followup_due_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ContactList:
    query = _active_contacts()
    filters = ContactListFilters(
        q=q,
        contact_type=contact_type,
        min_value_score=min_value_score,
        followup_due_only=followup_due_only,
        limit=limit,
        offset=offset,
    )
    if filters.q:
        search = f"%{filters.q.strip()}%"
        query = query.where(
            or_(
                Contact.name.ilike(search),
                Contact.email.ilike(search),
                Contact.company.ilike(search),
                Contact.role.ilike(search),
                Contact.notes.ilike(search),
            )
        )
    if filters.contact_type:
        query = query.where(func.lower(Contact.contact_type) == filters.contact_type.lower())
    if filters.min_value_score is not None:
        query = query.where(Contact.value_score >= filters.min_value_score)
    if filters.followup_due_only:
        query = query.where(Contact.next_followup_date <= date.today())

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(desc(Contact.value_score), desc(Contact.created_at))
        .offset(filters.offset)
        .limit(filters.limit)
    )
    items = [ContactOut.model_validate(item) for item in result.scalars().all()]
    return ContactList(total=int(total or 0), items=items)


@router.get("/stats", response_model=ContactStats)
async def contact_stats(db: DbSession) -> ContactStats:
    base = _active_contacts()
    total = int(await db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    leads = int(
        await db.scalar(
            select(func.count(Contact.id)).where(
                Contact.is_deleted.is_(False),
                func.lower(Contact.contact_type) == "lead",
            )
        )
        or 0
    )
    with_email = int(
        await db.scalar(
            select(func.count(Contact.id)).where(
                Contact.is_deleted.is_(False),
                Contact.email.is_not(None),
                Contact.email != "",
            )
        )
        or 0
    )
    followup_due = int(
        await db.scalar(
            select(func.count(Contact.id)).where(
                Contact.is_deleted.is_(False),
                Contact.next_followup_date <= date.today(),
            )
        )
        or 0
    )
    type_rows = await db.execute(
        select(Contact.contact_type, func.count(Contact.id))
        .where(Contact.is_deleted.is_(False))
        .group_by(Contact.contact_type)
    )
    return ContactStats(
        total=total,
        leads=leads,
        with_email=with_email,
        followup_due=followup_due,
        by_type={str(row[0] or "unknown"): int(row[1]) for row in type_rows},
    )


@router.post("", response_model=ContactOut, status_code=201)
async def create_contact(data: ContactCreate, db: DbSession):
    row = Contact(
        name=data.name,
        email=data.email,
        company=data.company,
        role=data.role,
        linkedin_url=data.linkedin_url,
        telegram_handle=data.telegram_handle,
        notes=data.notes,
        contact_type=data.contact_type,
        value_score=data.value_score,
        next_followup_date=data.next_followup_date,
        followup_reason=data.followup_reason,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await event_bus.emit(
        "contact.created",
        {"contact_id": str(row.id), "name": row.name, "contact_type": row.contact_type},
    )
    return ContactOut.model_validate(row)


@router.post("/bulk", response_model=ContactBulkResult, status_code=201)
async def bulk_upsert_contacts(items: list[ContactCreate], db: DbSession) -> ContactBulkResult:
    created = 0
    updated = 0
    out: list[ContactOut] = []

    for item in items:
        email = (item.email or "").strip().lower() or None
        existing = None
        if email:
            existing = (
                await db.execute(
                    _active_contacts().where(Contact.email == email).limit(1)
                )
            ).scalar_one_or_none()
        if existing:
            existing.name = item.name or existing.name
            existing.email = email or existing.email
            existing.company = item.company or existing.company
            existing.role = item.role or existing.role
            existing.linkedin_url = item.linkedin_url or existing.linkedin_url
            existing.telegram_handle = item.telegram_handle or existing.telegram_handle
            existing.notes = item.notes or existing.notes
            existing.contact_type = item.contact_type or existing.contact_type
            existing.value_score = item.value_score or existing.value_score
            existing.next_followup_date = item.next_followup_date or existing.next_followup_date
            existing.followup_reason = item.followup_reason or existing.followup_reason
            updated += 1
            out.append(ContactOut.model_validate(existing))
            continue

        row = Contact(
            name=item.name,
            email=email,
            company=item.company,
            role=item.role,
            linkedin_url=item.linkedin_url,
            telegram_handle=item.telegram_handle,
            notes=item.notes,
            contact_type=item.contact_type or "lead",
            value_score=item.value_score,
            next_followup_date=item.next_followup_date,
            followup_reason=item.followup_reason,
        )
        db.add(row)
        await db.flush()
        await event_bus.emit(
            "contact.created",
            {"contact_id": str(row.id), "name": row.name, "contact_type": row.contact_type},
        )
        created += 1
        out.append(ContactOut.model_validate(row))

    await db.commit()
    return ContactBulkResult(created=created, updated=updated, items=out)


@router.get("/{contact_id}", response_model=ContactOut)
async def get_contact(contact_id: UUID, db: DbSession):
    row = (
        await db.execute(_active_contacts().where(Contact.id == contact_id).limit(1))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return ContactOut.model_validate(row)


@router.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(contact_id: UUID, data: ContactUpdate, db: DbSession) -> ContactOut:
    row = (
        await db.execute(_active_contacts().where(Contact.id == contact_id).limit(1))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(row)
    await event_bus.emit(
        "contact.updated",
        {"contact_id": str(row.id), "name": row.name, "contact_type": row.contact_type},
    )
    return ContactOut.model_validate(row)


@router.delete("/{contact_id}", status_code=204)
async def delete_contact(contact_id: UUID, db: DbSession) -> None:
    row = (
        await db.execute(_active_contacts().where(Contact.id == contact_id).limit(1))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    row.is_deleted = True
    row.deleted_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await event_bus.emit("contact.deleted", {"contact_id": str(row.id), "name": row.name})
