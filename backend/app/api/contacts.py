from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.contact import Contact
from app.schemas.contact import ContactCreate, ContactOut

router = APIRouter(prefix="/contacts", tags=["contacts"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class ContactList(BaseModel):
    total: int
    items: list[ContactOut]


def _active_contacts():
    return select(Contact).where(Contact.is_deleted.is_(False))


@router.get("", response_model=ContactList)
async def list_contacts(db: DbSession) -> ContactList:
    query = _active_contacts()
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(query.order_by(desc(Contact.created_at)))
    items = [ContactOut.model_validate(item) for item in result.scalars().all()]
    return ContactList(total=int(total or 0), items=items)


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
    return ContactOut.model_validate(row)


@router.get("/{contact_id}", response_model=ContactOut)
async def get_contact(contact_id: UUID, db: DbSession):
    row = (
        await db.execute(_active_contacts().where(Contact.id == contact_id).limit(1))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return ContactOut.model_validate(row)
