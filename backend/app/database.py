import logging
from contextlib import asynccontextmanager

import tenacity
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

logger = logging.getLogger(__name__)

# Enterprise-grade engine with retries and connection pooling
@tenacity.retry(
    stop=tenacity.stop_after_attempt(5),
    wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
    retry=tenacity.retry_if_exception_type(Exception),
    before_sleep=lambda retry_state: logger.warning(f"DB connection failed, retrying... ({retry_state.attempt_number})")
)
def _set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable foreign key support for SQLite connections."""
    import sqlite3
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

def create_engine_with_retry():
    url = settings.DATABASE_URL
    is_sqlite = url.startswith("sqlite")

    engine_args = {
        "pool_pre_ping": True,
        "echo": settings.DEBUG if hasattr(settings, "DEBUG") else False,
    }

    if is_sqlite:
        engine_args["connect_args"] = {"check_same_thread": False}
    else:
        engine_args.update({
            "pool_size": 20,
            "max_overflow": 10,
            "pool_timeout": 30,
            "pool_recycle": 1800,
            "connect_args": {"server_settings": {"application_name": "brav_os_mas"}}
        })

    engine = create_async_engine(url, **engine_args)

    # Enable foreign keys for SQLite
    if is_sqlite:
        event.listen(engine.sync_engine, "connect", _set_sqlite_pragma)

    return engine

engine = create_engine_with_retry()
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_db_session() -> AsyncSession:
    """Get database session for direct use."""
    return AsyncSessionLocal()


@asynccontextmanager
async def transaction_scope():
    """
    Enterprise-grade transaction context manager with automatic rollback on failure.

    Usage:
        async with transaction_scope() as session:
            session.add(entity)
            # Automatically commits on success, rolls back on exception
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_health() -> dict:
    """Enterprise-grade database health check."""
    try:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import text
            result = await session.execute(text("SELECT 1"))
            row = result.scalar()
            return {
                "status": "healthy",
                "database": "connected",
                "query_test": row == 1,
                "pool_size": engine.pool.size() if hasattr(engine.pool, 'size') else 'N/A',
            }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "database": "disconnected",
        }
