"""
DataLoaders for GraphQL N+1 Query Optimization

Implements the DataLoader pattern to batch and cache database queries.
This prevents the N+1 problem when resolving nested GraphQL fields.
"""

from collections import defaultdict
from typing import List, Optional
from uuid import UUID

import aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.organization import Organization
from app.models.opportunity import Opportunity


class DataLoader:
    """Base DataLoader with batching and caching."""
    
    def __init__(self, db: AsyncSession, redis: Optional[aioredis.Redis] = None):
        self.db = db
        self.redis = redis
        self._cache = {}
        self._pending = defaultdict(list)
        self._batch_load_fn = None
    
    async def load(self, key: UUID) -> Optional:
        """Load a single item by key."""
        # Check cache
        cache_key = str(key)
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Add to pending batch
        self._pending[self._batch_load_fn].append(key)
        
        # Schedule batch load (in real implementation, use proper batching)
        # For now, immediate load
        results = await self._batch_load(list(self._pending[self._batch_load_fn]))
        self._pending[self._batch_load_fn].clear()
        
        # Cache and return
        for k, v in results.items():
            self._cache[str(k)] = v
        
        return results.get(key)
    
    async def load_many(self, keys: List[UUID]) -> List[Optional]:
        """Load multiple items by keys."""
        results = await self._batch_load(keys)
        return [results.get(k) for k in keys]
    
    async def _batch_load(self, keys: List[UUID]) -> dict:
        """Override in subclass."""
        raise NotImplementedError
    
    def clear(self, key: UUID):
        """Clear item from cache."""
        self._cache.pop(str(key), None)
    
    def clear_all(self):
        """Clear all cached items."""
        self._cache.clear()


class UserLoader(DataLoader):
    """DataLoader for User entities."""
    
    async def _batch_load(self, keys: List[UUID]) -> dict[UUID, Optional[User]]:
        """Batch load users by IDs."""
        if not keys:
            return {}
        
        result = await self.db.execute(
            select(User).where(User.id.in_(keys))
        )
        users = result.scalars().all()
        
        return {user.id: user for user in users}


class OrganizationLoader(DataLoader):
    """DataLoader for Organization entities."""
    
    async def _batch_load(self, keys: List[UUID]) -> dict[UUID, Optional[Organization]]:
        """Batch load organizations by IDs."""
        if not keys:
            return {}
        
        result = await self.db.execute(
            select(Organization).where(Organization.id.in_(keys))
        )
        orgs = result.scalars().all()
        
        return {org.id: org for org in orgs}


class OrganizationMembersLoader(DataLoader):
    """DataLoader for organization members."""
    
    async def _batch_load(self, keys: List[UUID]) -> dict[UUID, List[User]]:
        """Batch load organization members."""
        if not keys:
            return {}
        
        result = await self.db.execute(
            select(User).where(User.organization_id.in_(keys))
        )
        users = result.scalars().all()
        
        # Group by organization
        members = defaultdict(list)
        for user in users:
            members[user.organization_id].append(user)
        
        return {key: members.get(key, []) for key in keys}


class OpportunityLoader(DataLoader):
    """DataLoader for Opportunity entities."""
    
    async def _batch_load(self, keys: List[UUID]) -> dict[UUID, Optional[Opportunity]]:
        """Batch load opportunities by IDs."""
        if not keys:
            return {}
        
        result = await self.db.execute(
            select(Opportunity).where(Opportunity.id.in_(keys))
        )
        opportunities = result.scalars().all()
        
        return {opp.id: opp for opp in opportunities}


class Loaders:
    """Container for all DataLoaders."""
    
    def __init__(self, db: AsyncSession, redis: Optional[aioredis.Redis] = None):
        self.user = UserLoader(db, redis)
        self.organization = OrganizationLoader(db, redis)
        self.organization_members = OrganizationMembersLoader(db, redis)
        self.opportunity = OpportunityLoader(db, redis)
