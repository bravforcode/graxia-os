"""Auto-remediation tests — known-recoverable incidents retried + resolved."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.auto_remediation import auto_remediation_with_db
from ..enums import ChannelType, IncidentSeverity
from ..models import ChannelConnection, IncidentEvent


def _incident(db_session, source, title, severity=IncidentSeverity.MEDIUM):
    incident = IncidentEvent(title=title, description="d", severity=severity,
                             source=source)
    db_session.add(incident)
    return incident


@pytest.mark.asyncio
async def test_channel_health_incident_recovered_by_poll(db_session: AsyncSession, monkeypatch):
    conn = ChannelConnection(channel=ChannelType.SHOPEE, name="s",
                             last_sync_at=datetime.now(timezone.utc) - timedelta(days=3),
                             config={"mode": "sandbox"})
    db_session.add(conn)
    incident = _incident(db_session, "channel_health",
                         "Channel sync stale: shopee")
    await db_session.commit()
    calls = {"n": 0}

    async def _fake_poll(db, channel, since=None):
        calls["n"] += 1
        assert channel == ChannelType.SHOPEE
        return {"fetched": 0, "imported": 0, "reconcile": {"updated": 0, "skipped": 0}}

    monkeypatch.setattr(
        "graxia.packages.revenue_os.agents.auto_remediation._poll_channel", _fake_poll)
    result = await auto_remediation_with_db(db_session)
    assert result["recovered"] == 1 and result["failed"] == 0
    assert calls["n"] == 1
    await db_session.refresh(incident)
    assert incident.status == "resolved" and incident.resolved_at is not None


@pytest.mark.asyncio
async def test_failing_poll_keeps_incident_open(db_session: AsyncSession, monkeypatch):
    incident = _incident(db_session, "channel_health", "Channel sync stale: shopee")
    await db_session.commit()

    async def _fake_poll(db, channel, since=None):
        return {"skipped": True, "reason": "error: boom"}

    monkeypatch.setattr(
        "graxia.packages.revenue_os.agents.auto_remediation._poll_channel", _fake_poll)
    result = await auto_remediation_with_db(db_session)
    assert result["recovered"] == 0 and result["failed"] == 1
    await db_session.refresh(incident)
    assert incident.status == "open"  # human attention still needed


@pytest.mark.asyncio
async def test_unknown_source_not_handled(db_session: AsyncSession):
    _incident(db_session, "affiliate", "some affiliate incident")
    await db_session.commit()
    result = await auto_remediation_with_db(db_session)
    assert result == {"skipped": False, "checked": 0, "recovered": 0, "failed": 0}
    incident = await db_session.scalar(select(IncidentEvent))
    assert incident.status == "open"


@pytest.mark.asyncio
async def test_low_severity_not_remediated(db_session: AsyncSession):
    _incident(db_session, "channel_health", "Channel sync stale: shopee",
              severity=IncidentSeverity.LOW)
    await db_session.commit()
    result = await auto_remediation_with_db(db_session)
    assert result["checked"] == 0
