from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.agents.competition_scout import CompetitionScout
from app.agents.lead_hunter import LeadHunter
from app.config import settings

ORG_ID = UUID("00000000-0000-4000-8000-000000000042")


def _session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _session_factory(session: MagicMock):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


async def test_competition_scout_saves_opportunity_under_automation_org():
    session = _session()
    with patch.object(settings, "AUTOMATION_ORGANIZATION_ID", ORG_ID), patch(
        "app.database.AsyncSessionLocal", _session_factory(session)
    ):
        await CompetitionScout()._save_opportunity({"source_hash": "hash-scout", "title": "Hackathon"})

    assert session.add.call_args.args[0].organization_id == ORG_ID


async def test_lead_hunter_saves_lead_under_automation_org():
    session = _session()
    with patch.object(settings, "AUTOMATION_ORGANIZATION_ID", ORG_ID), patch(
        "app.database.AsyncSessionLocal", _session_factory(session)
    ), patch("app.core.career.upsert_job_posting_from_opportunity", AsyncMock()):
        await LeadHunter()._save_lead({"source_hash": "hash-lead", "title": "Freelance job"})

    assert session.add.call_args.args[0].organization_id == ORG_ID
