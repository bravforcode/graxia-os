"""
Draft Repository Implementation
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import Repository
from app.models.content_draft import ContentDraft
from app.core.specifications import Specification


class DraftRepository(Repository[ContentDraft]):
    """Repository for ContentDraft entities."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, id: UUID) -> Optional[ContentDraft]:
        """Get draft by ID."""
        return await self.session.get(ContentDraft, id)
    
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[ContentDraft]:
        """Get all drafts with pagination."""
        query = (
            select(ContentDraft)
            .order_by(desc(ContentDraft.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def add(self, entity: ContentDraft) -> ContentDraft:
        """Add new draft."""
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity
    
    async def update(self, entity: ContentDraft) -> ContentDraft:
        """Update existing draft."""
        await self.session.flush()
        await self.session.refresh(entity)
        return entity
    
    async def delete(self, id: UUID) -> bool:
        """Delete draft by ID."""
        entity = await self.get_by_id(id)
        if entity:
            await self.session.delete(entity)
            await self.session.flush()
            return True
        return False
    
    async def find(self, specification: Specification[ContentDraft]) -> List[ContentDraft]:
        """Find drafts matching specification."""
        query = select(ContentDraft).order_by(desc(ContentDraft.created_at))
        result = await self.session.execute(query)
        all_drafts = list(result.scalars().all())
        
        # Filter using specification
        return [draft for draft in all_drafts if specification.is_satisfied_by(draft)]
    
    async def count(self) -> int:
        """Count total drafts."""
        from sqlalchemy import func
        query = select(func.count()).select_from(ContentDraft)
        result = await self.session.execute(query)
        return result.scalar() or 0
    
    async def exists(self, id: UUID) -> bool:
        """Check if draft exists."""
        entity = await self.get_by_id(id)
        return entity is not None
    
    async def find_by_status(self, status: str, limit: int = 100) -> List[ContentDraft]:
        """Find drafts by status."""
        query = (
            select(ContentDraft)
            .where(ContentDraft.status == status)
            .order_by(desc(ContentDraft.created_at))
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def find_pending(self, limit: int = 100) -> List[ContentDraft]:
        """Find pending drafts."""
        return await self.find_by_status("pending", limit)
    
    async def count_by_status(self, status: str) -> int:
        """Count drafts by status."""
        from sqlalchemy import func
        query = (
            select(func.count())
            .select_from(ContentDraft)
            .where(ContentDraft.status == status)
        )
        result = await self.session.execute(query)
        return result.scalar() or 0
