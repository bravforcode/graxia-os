"""
graxia/packages/revenue_os/db.py
Unified database session management - uses backend session factory when available
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Try to import from backend to ensure single source of truth
try:
    import sys
    from pathlib import Path
    
    # Add backend to path if not already there
    backend_path = Path(__file__).resolve().parents[3] / "backend"
    if backend_path.exists() and str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))
    
    from app.database import AsyncSessionLocal as _backend_AsyncSessionLocal

    # Backend's get_db_session() returns a bare session (not a context manager),
    # which breaks `async with get_db_session() as db` used across revenue_os
    # (API lifespan, Celery tasks). Keep the backend engine/sessionmaker as the
    # single source of truth, but restore the revenue_os context-manager contract.
    @asynccontextmanager
    async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager that yields a session and handles commit/rollback.
        Use this in Celery tasks and non-FastAPI code.

        Example:
            async with get_db_session() as db:
                db.add(my_model)
        """
        async with _backend_AsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def get_db() -> AsyncGenerator[AsyncSession, None]:
        """
        FastAPI dependency. Injects a session that auto-commits or rolls back.

        Example:
            @router.post("/")
            async def create(db: AsyncSession = Depends(get_db)):
                ...
        """
        async with get_db_session() as session:
            yield session
    
    logger.info("Using backend database session factory")
    USING_BACKEND_SESSION = True
except ImportError as e:
    logger.warning(f"Backend database module not available: {e}, using fallback")
    USING_BACKEND_SESSION = False
    
    # Fallback implementation
    from sqlalchemy.ext.asyncio import (
        async_sessionmaker,
        create_async_engine,
    )
    
    def _get_database_url() -> str:
        url = os.getenv("DATABASE_URL")
        if not url:
            env = os.getenv("APP_ENV", "development")
            if env == "production":
                raise RuntimeError(
                    "DATABASE_URL environment variable is required in production. "
                    "Format: postgresql+asyncpg://user:pass@host:5432/dbname"
                )
            # Dev fallback
            return "postgresql+asyncpg://graxia:graxia@localhost:5432/graxia_dev"
        return url

    _DATABASE_URL: str | None = None

    def _get_or_init_database_url() -> str:
        global _DATABASE_URL
        if _DATABASE_URL is None:
            _DATABASE_URL = _get_database_url()
        return _DATABASE_URL

    _engine = None
    _AsyncSessionLocal = None

    def _get_engine():
        global _engine, _AsyncSessionLocal
        if _engine is None:
            database_url = _get_or_init_database_url()
            _engine = create_async_engine(
                database_url,
                pool_size=int(os.getenv("DATABASE_POOL_SIZE", "10")),
                max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "20")),
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=os.getenv("APP_ENV") == "development",
            )
            _AsyncSessionLocal = async_sessionmaker(
                _engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        return _engine

    def _get_sessionmaker():
        _get_engine()
        return _AsyncSessionLocal


    @asynccontextmanager
    async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager that yields a session and handles commit/rollback.
        Use this in Celery tasks and non-FastAPI code.

        Example:
            async with get_db_session() as db:
                db.add(my_model)
        """
        async with _get_sessionmaker()() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise


    async def get_db() -> AsyncGenerator[AsyncSession, None]:
        """
        FastAPI dependency. Injects a session that auto-commits or rolls back.

        Example:
            @router.post("/")
            async def create(db: AsyncSession = Depends(get_db)):
                ...
        """
        async with get_db_session() as session:
            yield session


def _resolve_database_url() -> str:
    """Public DATABASE_URL accessor — works in both backend and fallback modes."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    if not USING_BACKEND_SESSION:
        return _get_or_init_database_url()
    return "postgresql+asyncpg://graxia:graxia@localhost:5432/graxia_dev"


DATABASE_URL = _resolve_database_url()
