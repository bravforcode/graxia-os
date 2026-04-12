"""
Unit of Work Pattern

Maintains consistency across multiple repository operations.
"""
from abc import ABC, abstractmethod
from typing import Optional
import logging

from app.database import AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


class UnitOfWork(ABC):
    """Abstract Unit of Work."""
    
    @abstractmethod
    async def __aenter__(self):
        """Enter context manager."""
        pass
    
    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        pass
    
    @abstractmethod
    async def commit(self):
        """Commit transaction."""
        pass
    
    @abstractmethod
    async def rollback(self):
        """Rollback transaction."""
        pass


class SQLAlchemyUnitOfWork(UnitOfWork):
    """SQLAlchemy implementation of Unit of Work."""
    
    def __init__(self):
        self.session: Optional[AsyncSession] = None
    
    async def __aenter__(self):
        """Start transaction."""
        self.session = AsyncSessionLocal()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """End transaction."""
        if exc_type is not None:
            await self.rollback()
        else:
            try:
                await self.commit()
            except Exception as e:
                logger.error(f"Commit failed: {e}")
                await self.rollback()
                raise
        finally:
            if self.session:
                await self.session.close()
    
    async def commit(self):
        """Commit transaction."""
        if self.session:
            await self.session.commit()
            logger.debug("Transaction committed")
    
    async def rollback(self):
        """Rollback transaction."""
        if self.session:
            await self.session.rollback()
            logger.debug("Transaction rolled back")
