"""
Opportunity Repository Implementation
"""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import Repository
from app.models.opportunity import Opportunity
from app.core.specifications import Specification


class OpportunityRepository(Repository[Opportunity]):
    """Repository for Opportunity entities."""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    def _base_query(self):
        return select(Opportunity).where(Opportunity.is_deleted.is_(False))
    
    async def get_by_id(self, id: UUID) -> Optional[Opportunity]:
        """Get opportunity by ID."""
        result = await self.session.execute(
            self._base_query().where(Opportunity.id == id).limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Opportunity]:
        """Get all opportunities with pagination."""
        query = (
            self._base_query()
            .order_by(desc(Opportunity.total_score))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def add(self, entity: Opportunity) -> Opportunity:
        """Add new opportunity."""
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity
    
    async def update(self, entity: Opportunity) -> Opportunity:
        """Update existing opportunity."""
        await self.session.flush()
        await self.session.refresh(entity)
        return entity
    
    async def delete(self, id: UUID) -> bool:
        """Soft-delete opportunity by ID."""
        entity = await self.get_by_id(id)
        if entity:
            entity.is_deleted = True
            entity.deleted_at = datetime.now(timezone.utc)
            await self.session.flush()
            return True
        return False
    
    async def find(self, specification: Specification[Opportunity]) -> List[Opportunity]:
        """Find opportunities matching specification."""
        query = self._base_query().order_by(desc(Opportunity.total_score))
        result = await self.session.execute(query)
        all_opportunities = list(result.scalars().all())
        
        # Filter using specification
        return [opp for opp in all_opportunities if specification.is_satisfied_by(opp)]
    
    async def count(self) -> int:
        """Count total opportunities."""
        from sqlalchemy import func
        query = select(func.count()).select_from(
            select(Opportunity.id)
            .where(Opportunity.is_deleted.is_(False))
            .subquery()
        )
        result = await self.session.execute(query)
        return result.scalar() or 0
    
    async def exists(self, id: UUID) -> bool:
        """Check if opportunity exists."""
        entity = await self.get_by_id(id)
        return entity is not None
    
    async def find_by_status(self, status: str, limit: int = 100) -> List[Opportunity]:
        """Find opportunities by status."""
        query = (
            self._base_query()
            .where(Opportunity.status == status)
            .order_by(desc(Opportunity.total_score))
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def find_high_score(self, threshold: float = 80.0, limit: int = 10) -> List[Opportunity]:
        """Find high-scoring opportunities."""
        query = (
            self._base_query()
            .where(Opportunity.total_score >= threshold)
            .order_by(desc(Opportunity.total_score))
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
