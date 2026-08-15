import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import importlib
from ..celery.tasks.incident_alerter import alerter_sweep
_alerter_mod = importlib.import_module("graxia.packages.revenue_os.celery.tasks.incident_alerter")
from ..enums import IncidentSeverity
from ..models import IncidentEvent


@pytest.mark.asyncio
async def test_alerter_sends_medium_incidents_once(db_session: AsyncSession, monkeypatch):
    db_session.add(IncidentEvent(title="boom", description="x", severity=IncidentSeverity.MEDIUM))
    await db_session.commit()

    sent = []

    class FakeNotifier:
        @staticmethod
        async def notify_system_alert(severity, msg):
            sent.append((severity, msg))
            return True

    monkeypatch.setattr(_alerter_mod, "notifier", FakeNotifier)
    result = await alerter_sweep(db_session)
    assert result["sent"] == 1
    incident = await db_session.scalar(select(IncidentEvent))
    assert incident.notified_at is not None

    result2 = await alerter_sweep(db_session)
    assert result2["sent"] == 0  # not sent twice


@pytest.mark.asyncio
async def test_alerter_skips_low_severity(db_session: AsyncSession, monkeypatch):
    db_session.add(IncidentEvent(title="minor", description="x", severity=IncidentSeverity.LOW))
    await db_session.commit()

    class FakeNotifier:
        @staticmethod
        def notify_system_alert(severity, msg):
            raise AssertionError("LOW should not alert")

    monkeypatch.setattr(_alerter_mod, "notifier", FakeNotifier)
    result = await alerter_sweep(db_session)
    assert result["sent"] == 0
