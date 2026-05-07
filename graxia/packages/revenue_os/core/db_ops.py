"""
Revenue OS Database Operations
Atomic operations, savepoints, and distributed locks
"""
import os
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional
import structlog

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from ..models import AutomationLock
from ..constants import AUTOMATION_LOCK_TTL_MINUTES

logger = structlog.get_logger()


@asynccontextmanager
async def acquire_automation_lock(
    db: AsyncSession,
    lock_name: str,
    ttl_seconds: int = AUTOMATION_LOCK_TTL_MINUTES * 60,
    worker_id: Optional[str] = None,
):
    """
    Distributed lock using PostgreSQL.
    Uses INSERT with unique constraint to prevent cross-worker overlap.
    
    Usage:
        async with acquire_automation_lock(db, "daily_revenue_ops") as acquired:
            if not acquired:
                logger.info("Lock held by another worker, skipping")
                return
            # do work
    
    Args:
        db: Database session
        lock_name: Unique lock identifier
        ttl_seconds: Lock time-to-live in seconds
        worker_id: Worker identifier (defaults to PID@hostname)
    
    Yields:
        bool: True if lock acquired, False otherwise
    """
    worker_id = worker_id or f"{os.getpid()}@{socket.gethostname()}"
    locked_until = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    acquired = False
    
    try:
        # Delete expired locks first
        await db.execute(
            delete(AutomationLock).where(
                AutomationLock.locked_until < datetime.utcnow()
            )
        )
        await db.commit()
        
        # Attempt to acquire lock
        try:
            async with db.begin_nested():  # Savepoint
                lock = AutomationLock(
                    name=lock_name,
                    owner=worker_id,
                    locked_by_worker=worker_id,
                    locked_until=locked_until,
                )
                db.add(lock)
                await db.flush()
            acquired = True
            logger.info(
                "automation_lock_acquired",
                lock_name=lock_name,
                worker_id=worker_id,
                ttl_seconds=ttl_seconds,
            )
        except IntegrityError:
            # Lock already held by another worker
            await db.rollback()
            acquired = False
            
            # Log who holds the lock
            result = await db.execute(
                select(AutomationLock).where(AutomationLock.name == lock_name)
            )
            existing_lock = result.scalar_one_or_none()
            if existing_lock:
                logger.warning(
                    "automation_lock_held_by_another",
                    lock_name=lock_name,
                    held_by=existing_lock.owner,
                    locked_until=existing_lock.locked_until.isoformat(),
                    current_worker=worker_id,
                )
            else:
                logger.warning(
                    "automation_lock_acquisition_failed",
                    lock_name=lock_name,
                    worker_id=worker_id,
                    reason="IntegrityError but lock not found",
                )
        
        yield acquired
        
    finally:
        if acquired:
            # Release lock
            try:
                await db.execute(
                    delete(AutomationLock).where(AutomationLock.name == lock_name)
                )
                await db.commit()
                logger.info(
                    "automation_lock_released",
                    lock_name=lock_name,
                    worker_id=worker_id,
                )
            except Exception as e:
                logger.error(
                    "automation_lock_release_failed",
                    lock_name=lock_name,
                    worker_id=worker_id,
                    error=str(e),
                )


async def update_lock_heartbeat(
    db: AsyncSession,
    lock_name: str,
) -> bool:
    """
    Update lock heartbeat to prevent expiry during long-running tasks.
    
    Args:
        db: Database session
        lock_name: Lock identifier
    
    Returns:
        bool: True if heartbeat updated, False if lock not found
    """
    result = await db.execute(
        select(AutomationLock).where(AutomationLock.name == lock_name)
    )
    lock = result.scalar_one_or_none()
    
    if not lock:
        return False
    
    lock.heartbeat_at = datetime.utcnow()
    await db.commit()
    
    logger.debug(
        "automation_lock_heartbeat",
        lock_name=lock_name,
        owner=lock.owner,
    )
    return True


async def cleanup_expired_locks(db: AsyncSession) -> int:
    """
    Cleanup expired automation locks.
    Should be called periodically by maintenance task.
    
    Args:
        db: Database session
    
    Returns:
        int: Number of locks cleaned up
    """
    result = await db.execute(
        delete(AutomationLock)
        .where(AutomationLock.locked_until < datetime.utcnow())
        .returning(AutomationLock.name)
    )
    deleted_locks = result.scalars().all()
    await db.commit()
    
    if deleted_locks:
        logger.info(
            "automation_locks_cleaned",
            count=len(deleted_locks),
            locks=list(deleted_locks),
        )
    
    return len(deleted_locks)


@asynccontextmanager
async def atomic_operation(db: AsyncSession):
    """
    Context manager for atomic database operations using savepoints.
    
    Usage:
        async with atomic_operation(db):
            # Multiple DB operations
            # All succeed or all rollback
    """
    async with db.begin_nested():  # Creates a savepoint
        try:
            yield
        except Exception:
            await db.rollback()
            raise
