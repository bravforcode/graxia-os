from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.services.audit_service import log_audit_event


@pytest.mark.asyncio
async def test_log_audit_event_without_db_persists_to_fixture_database(engine):
    action = f"fixture-engine-{uuid4()}"

    await log_audit_event(
        action=action,
        event_type="test.fixture",
        event_category="test",
    )

    async with engine.connect() as connection:
        stored_action = await connection.scalar(
            select(AuditLog.action).where(AuditLog.action == action)
        )

    assert stored_action == action
