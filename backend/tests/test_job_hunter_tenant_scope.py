from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.agents.job_hunter import JobHunterAgent
from app.config import settings

ORG_ID = UUID("00000000-0000-4000-8000-000000000042")


async def test_job_hunter_saves_job_under_automation_org():
    session = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    @asynccontextmanager
    async def factory():
        yield session

    with patch.object(settings, "AUTOMATION_ORGANIZATION_ID", ORG_ID), patch(
        "app.agents.job_hunter.AsyncSessionLocal", factory
    ):
        await JobHunterAgent()._save_job({"title": "Backend role", "source_hash": "hash-job"})

    assert session.add.call_args.args[0].organization_id == ORG_ID
