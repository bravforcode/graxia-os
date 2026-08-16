"""poll_channel tests — shared poll path (task + admin backfill route)."""
import importlib

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ..celery.tasks.marketplace_poll import poll_channel
from ..enums import ChannelType
from ..models import ChannelConnection

# tasks/__init__ rebinds the submodule name to the function, so reach the
# real module through sys.modules:
MP_MOD = importlib.import_module(
    "graxia.packages.revenue_os.celery.tasks.marketplace_poll")


@pytest.mark.asyncio
async def test_poll_channel_imports_and_updates_cursor(db_session: AsyncSession, monkeypatch):
    conn = ChannelConnection(channel=ChannelType.SHOPEE, name="shopee-store",
                             config={"mode": "sandbox"})
    db_session.add(conn)
    await db_session.commit()
    calls = {}

    class _FakeAdapter:
        def __init__(self, config):
            calls["config"] = config

        async def import_orders(self, since=None):
            calls["since"] = since
            return [{"platform_order_id": "p1", "customer_email": "b@example.com",
                     "amount_cents": 1000, "currency": "THB", "product_id": None,
                     "status": "paid", "metadata": {}}]

    async def _fake_reconcile(db, external):
        calls["external"] = external
        return {"updated": 0, "skipped": 1}

    async def _fake_import(db, platform, orders):
        calls["platform"] = platform
        calls["orders"] = orders
        return 1

    monkeypatch.setattr(MP_MOD, "ADAPTERS", {ChannelType.SHOPEE: (_FakeAdapter, _fake_reconcile)})
    monkeypatch.setattr(MP_MOD, "import_channel_orders", _fake_import)
    result = await poll_channel(db_session, ChannelType.SHOPEE)
    await db_session.commit()
    assert result == {"fetched": 1, "imported": 1, "reconcile": {"updated": 0, "skipped": 1}}
    assert calls["platform"] == "shopee"
    assert calls["external"] == {"p1": "paid"}
    await db_session.refresh(conn)
    assert conn.config["last_import_at"] is not None  # cursor advanced


@pytest.mark.asyncio
async def test_poll_channel_uses_explicit_since_for_backfill(db_session: AsyncSession, monkeypatch):
    conn = ChannelConnection(channel=ChannelType.LAZADA, name="lazada-store",
                             config={"mode": "sandbox", "last_import_at": "2026-01-01T00:00:00+00:00"})
    db_session.add(conn)
    await db_session.commit()
    seen = {}

    class _FakeAdapter:
        def __init__(self, config):
            pass

        async def import_orders(self, since=None):
            seen["since"] = since
            return []

    async def _fake_reconcile(db, external):
        return {"updated": 0, "skipped": 0}

    monkeypatch.setattr(MP_MOD, "ADAPTERS", {ChannelType.LAZADA: (_FakeAdapter, _fake_reconcile)})
    await poll_channel(db_session, ChannelType.LAZADA, since="2026-02-01T00:00:00+00:00")
    assert seen["since"] == "2026-02-01T00:00:00+00:00"  # explicit backfill wins


@pytest.mark.asyncio
async def test_poll_channel_defaults_to_config_cursor(db_session: AsyncSession, monkeypatch):
    conn = ChannelConnection(channel=ChannelType.SHOPEE, name="shopee-store",
                             config={"mode": "sandbox", "last_import_at": "2026-01-01T00:00:00+00:00"})
    db_session.add(conn)
    await db_session.commit()
    seen = {}

    class _FakeAdapter:
        def __init__(self, config):
            pass

        async def import_orders(self, since=None):
            seen["since"] = since
            return []

    async def _fake_reconcile(db, external):
        return {"updated": 0, "skipped": 0}

    monkeypatch.setattr(MP_MOD, "ADAPTERS", {ChannelType.SHOPEE: (_FakeAdapter, _fake_reconcile)})
    await poll_channel(db_session, ChannelType.SHOPEE)
    assert seen["since"] == "2026-01-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_poll_channel_skips_disconnected(db_session: AsyncSession):
    result = await poll_channel(db_session, ChannelType.AMAZON)  # no row
    assert result == {"skipped": True, "reason": "not_connected"}


@pytest.mark.asyncio
async def test_poll_channel_isolates_errors(db_session: AsyncSession, monkeypatch):
    conn = ChannelConnection(channel=ChannelType.TIKTOK_SHOP, name="tt-store",
                             config={"mode": "sandbox"})
    db_session.add(conn)
    await db_session.commit()

    class _BoomAdapter:
        def __init__(self, config):
            pass

        async def import_orders(self, since=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(MP_MOD, "ADAPTERS", {ChannelType.TIKTOK_SHOP: (_BoomAdapter, None)})
    result = await poll_channel(db_session, ChannelType.TIKTOK_SHOP)
    assert result["skipped"] is True
    assert "boom" in result["reason"]
