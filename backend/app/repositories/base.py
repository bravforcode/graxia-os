"""
Repository Pattern

Abstract data access layer with clean interfaces.
"""
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List
from uuid import UUID

from app.core.specifications import Specification


T = TypeVar('T')


class Repository(ABC, Generic[T]):
    """Base repository interface."""
    
    @abstractmethod
    async def get_by_id(self, id: UUID) -> Optional[T]:
        """Get entity by ID."""
        pass
    
    @abstractmethod
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """Get all entities with pagination."""
        pass
    
    @abstractmethod
    async def add(self, entity: T) -> T:
        """Add new entity."""
        pass
    
    @abstractmethod
    async def update(self, entity: T) -> T:
        """Update existing entity."""
        pass
    
    @abstractmethod
    async def delete(self, id: UUID) -> bool:
        """Delete entity by ID."""
        pass
    
    @abstractmethod
    async def find(self, specification: Specification[T]) -> List[T]:
        """Find entities matching specification."""
        pass
    
    @abstractmethod
    async def count(self) -> int:
        """Count total entities."""
        pass
    
    @abstractmethod
    async def exists(self, id: UUID) -> bool:
        """Check if entity exists."""
        pass
