"""Channel health tests — stale sync raises incident once, healthy silent."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..celery.tasks.channel_health import channel_health_with_db
from ..enums import ChannelType, IncidentSeverity
from ..models import ChannelConnection, IncidentEvent


def _conn(channel=ChannelType.SHOPEE, name="store", enabled=True, last=None,
          config=None) -> ChannelConnection:
    return ChannelConnection(channel=channel, name=name, enabled=enabled,
                             last_sync_at=last, config=config or {})


@pytest.mark.asyncio
async def test_stale_channel_raises_incident_once(db_session: AsyncSession):
    db_session.add(_conn(last=datetime.now(timezone.utc) - timedelta(days=3)))
    await db_session.commit()

    first = await channel_health_with_db(db_session)
    assert first == {"skipped": False, "healthy": 0, "stale": 1}
    incidents = (await db_session.execute(select(IncidentEvent))).scalars().all()
    assert len(incidents) == 1
    assert incidents[0].severity == IncidentSeverity.LOW
    assert incidents[0].source == "channel_health"
    assert "shopee" in incidents[0].title

    second = await channel_health_with_db(db_session)
    assert second["stale"] == 1
    assert (await db_session.execute(select(IncidentEvent))).scalars().all().__len__() == 1  # no dup


@pytest.mark.asyncio
async def test_fresh_channel_is_healthy(db_session: AsyncSession):
    db_session.add(_conn(last=datetime.now(timezone.utc) - timedelta(minutes=5)))
    await db_session.commit()
    result = await channel_health_with_db(db_session)
    assert result == {"skipped": False, "healthy": 1, "stale": 0}
    assert (await db_session.execute(select(IncidentEvent))).scalars().all() == []


@pytest.mark.asyncio
async def test_disabled_and_fx_channels_skipped(db_session: AsyncSession):
    db_session.add(_conn(enabled=False, last=datetime.now(timezone.utc) - timedelta(days=9)))
    db_session.add(_conn(channel=ChannelType.FX, name="fx-rates",
                         last=datetime.now(timezone.utc) - timedelta(days=9)))
    await db_session.commit()
    result = await channel_health_with_db(db_session)
    assert result == {"skipped": False, "healthy": 0, "stale": 0}
    assert (await db_session.execute(select(IncidentEvent))).scalars().all() == []


@pytest.mark.asyncio
async def test_never_synced_is_not_stale(db_session: AsyncSession):
    db_session.add(_conn(last=None))
    await db_session.commit()
    result = await channel_health_with_db(db_session)
    assert result == {"skipped": False, "healthy": 0, "stale": 0}
