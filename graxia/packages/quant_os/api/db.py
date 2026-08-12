"""
graxia/packages/quant_os/api/db.py
Database session management for trading API — standalone (no revenue_os dependency).
"""
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
    AsyncSession,
)

# Import models so they register on Base.metadata for Alembic / sync creation.
from .models import Base  # noqa: F401

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://graxia:graxia@localhost:5432/quant_os",
)

_engine = None
_SessionLocal = None


def _get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_async_engine(
            DATABASE_URL,
            pool_size=int(os.getenv("DATABASE_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "20")),
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=os.getenv("APP_ENV") == "development",
        )
        _SessionLocal = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _engine


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields async session with auto-commit/rollback."""
    engine = _get_engine()
    factory = _SessionLocal
    if factory is None:
        factory = getattr(engine, 'session', None)
    if factory is None:
        raise RuntimeError("No session factory available")
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
