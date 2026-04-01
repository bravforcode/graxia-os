from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.contact import Contact
from app.schemas.contact import ContactOut, ContactCreate

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=list[ContactOut])
async def list_contacts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contact).order_by(Contact.name))
    return result.scalars().all()


@router.post("", response_model=ContactOut, status_code=201)
async def create_contact(data: ContactCreate, db: AsyncSession = Depends(get_db)):
    contact = Contact(**data.model_dump())
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.get("/{contact_id}", response_model=ContactOut)
async def get_contact(contact_id: UUID, db: AsyncSession = Depends(get_db)):
    c = await db.get(Contact, contact_id)
    if not c:
        raise HTTPException(404, "Contact not found")
    return c
