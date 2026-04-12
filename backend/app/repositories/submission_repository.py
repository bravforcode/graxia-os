"""
Submission Repository Implementation
"""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import Repository
from app.models.submission import Submission
from app.core.specifications import Specification


class SubmissionRepository(Repository[Submission]):
    """Repository for Submission entities."""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    def _base_query(self):
        return select(Submission).where(Submission.is_deleted.is_(False))
    
    async def get_by_id(self, id: UUID) -> Optional[Submission]:
        """Get submission by ID."""
        result = await self.session.execute(
            self._base_query().where(Submission.id == id).limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Submission]:
        """Get all submissions with pagination."""
        query = (
            self._base_query()
            .order_by(desc(Submission.sent_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def add(self, entity: Submission) -> Submission:
        """Add new submission."""
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity
    
    async def update(self, entity: Submission) -> Submission:
        """Update existing submission."""
        await self.session.flush()
        await self.session.refresh(entity)
        return entity
    
    async def delete(self, id: UUID) -> bool:
        """Soft-delete submission by ID."""
        entity = await self.get_by_id(id)
        if entity:
            entity.is_deleted = True
            entity.deleted_at = datetime.now(timezone.utc)
            await self.session.flush()
            return True
        return False
    
    async def find(self, specification: Specification[Submission]) -> List[Submission]:
        """Find submissions matching specification."""
        query = self._base_query().order_by(desc(Submission.sent_at))
        result = await self.session.execute(query)
        all_submissions = list(result.scalars().all())
        
        # Filter using specification
        return [sub for sub in all_submissions if specification.is_satisfied_by(sub)]
    
    async def count(self) -> int:
        """Count total submissions."""
        from sqlalchemy import func
        query = select(func.count()).select_from(
            select(Submission.id)
            .where(Submission.is_deleted.is_(False))
            .subquery()
        )
        result = await self.session.execute(query)
        return result.scalar() or 0
    
    async def exists(self, id: UUID) -> bool:
        """Check if submission exists."""
        entity = await self.get_by_id(id)
        return entity is not None
    
    async def find_by_status(self, status: str, limit: int = 100) -> List[Submission]:
        """Find submissions by status."""
        query = (
            self._base_query()
            .where(Submission.status == status)
            .order_by(desc(Submission.sent_at))
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def find_by_opportunity(self, opportunity_id: UUID) -> List[Submission]:
        """Find submissions for an opportunity."""
        query = (
            self._base_query()
            .where(Submission.opportunity_id == opportunity_id)
            .order_by(desc(Submission.sent_at))
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
