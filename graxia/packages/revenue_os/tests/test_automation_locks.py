"""
Test Automation Locks
Verify distributed locking mechanism
"""
import pytest
import asyncio
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db_ops import acquire_automation_lock, cleanup_expired_locks
from ..models import AutomationLock


@pytest.mark.asyncio
async def test_lock_acquisition(db_session: AsyncSession):
    """Test that a lock can be acquired."""
    async with acquire_automation_lock(db_session, "test_lock") as acquired:
        assert acquired is True


@pytest.mark.asyncio
async def test_lock_prevents_concurrent_access(db_session: AsyncSession):
    """Test that a lock prevents concurrent access."""
    lock_name = "concurrent_test_lock"
    
    # First worker acquires lock
    async with acquire_automation_lock(db_session, lock_name) as acquired1:
        assert acquired1 is True
        
        # Second worker tries to acquire same lock (should fail)
        async with acquire_automation_lock(db_session, lock_name) as acquired2:
            assert acquired2 is False


@pytest.mark.asyncio
async def test_lock_released_after_context(db_session: AsyncSession):
    """Test that lock is released after context manager exits."""
    lock_name = "release_test_lock"
    
    # Acquire and release lock
    async with acquire_automation_lock(db_session, lock_name) as acquired:
        assert acquired is True
    
    # Should be able to acquire again
    async with acquire_automation_lock(db_session, lock_name) as acquired:
        assert acquired is True


@pytest.mark.asyncio
async def test_expired_locks_cleanup(db_session: AsyncSession):
    """Test that expired locks are cleaned up."""
    # Create an expired lock manually
    expired_lock = AutomationLock(
        name="expired_lock",
        owner="test_worker",
        locked_by_worker="test_worker",
        locked_until=datetime.utcnow() - timedelta(hours=1),  # Expired 1 hour ago
    )
    db_session.add(expired_lock)
    await db_session.commit()
    
    # Cleanup expired locks
    cleaned_count = await cleanup_expired_locks(db_session)
    
    assert cleaned_count == 1
    
    # Verify lock was deleted
    from sqlalchemy import select
    result = await db_session.execute(
        select(AutomationLock).where(AutomationLock.name == "expired_lock")
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_lock_with_custom_ttl(db_session: AsyncSession):
    """Test lock with custom TTL."""
    lock_name = "ttl_test_lock"
    ttl_seconds = 60
    
    async with acquire_automation_lock(db_session, lock_name, ttl_seconds=ttl_seconds) as acquired:
        assert acquired is True
        
        # Verify lock expiry time
        from sqlalchemy import select
        result = await db_session.execute(
            select(AutomationLock).where(AutomationLock.name == lock_name)
        )
        lock = result.scalar_one()
        
        # Lock should expire in approximately ttl_seconds
        time_until_expiry = (lock.locked_until - datetime.utcnow()).total_seconds()
        assert 55 <= time_until_expiry <= 65  # Allow 5 second tolerance
