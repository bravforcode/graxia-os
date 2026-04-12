"""
Contact Repository Implementation
"""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import Repository
from app.models.contact import Contact
from app.core.specifications import Specification


class ContactRepository(Repository[Contact]):
    """Repository for Contact entities."""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    def _base_query(self):
        return select(Contact).where(Contact.is_deleted.is_(False))
    
    async def get_by_id(self, id: UUID) -> Optional[Contact]:
        """Get contact by ID."""
        result = await self.session.execute(
            self._base_query().where(Contact.id == id).limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Contact]:
        """Get all contacts with pagination."""
        query = (
            self._base_query()
            .order_by(Contact.name)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def add(self, entity: Contact) -> Contact:
        """Add new contact."""
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity
    
    async def update(self, entity: Contact) -> Contact:
        """Update existing contact."""
        await self.session.flush()
        await self.session.refresh(entity)
        return entity
    
    async def delete(self, id: UUID) -> bool:
        """Soft-delete contact by ID."""
        entity = await self.get_by_id(id)
        if entity:
            entity.is_deleted = True
            entity.deleted_at = datetime.now(timezone.utc)
            await self.session.flush()
            return True
        return False
    
    async def find(self, specification: Specification[Contact]) -> List[Contact]:
        """Find contacts matching specification."""
        query = self._base_query().order_by(Contact.name)
        result = await self.session.execute(query)
        all_contacts = list(result.scalars().all())
        
        # Filter using specification
        return [contact for contact in all_contacts if specification.is_satisfied_by(contact)]
    
    async def count(self) -> int:
        """Count total contacts."""
        from sqlalchemy import func
        query = select(func.count()).select_from(
            select(Contact.id)
            .where(Contact.is_deleted.is_(False))
            .subquery()
        )
        result = await self.session.execute(query)
        return result.scalar() or 0
    
    async def exists(self, id: UUID) -> bool:
        """Check if contact exists."""
        entity = await self.get_by_id(id)
        return entity is not None
    
    async def find_by_email(self, email: str) -> Optional[Contact]:
        """Find contact by email."""
        query = self._base_query().where(Contact.email == email)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def find_by_company(self, company: str, limit: int = 100) -> List[Contact]:
        """Find contacts by company."""
        query = (
            self._base_query()
            .where(Contact.company == company)
            .order_by(Contact.name)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
