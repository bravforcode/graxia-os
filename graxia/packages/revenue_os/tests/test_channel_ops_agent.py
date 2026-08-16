"""ChannelOpsAgent tests — autonomy gating + per-channel poll cycle."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.channel_ops import ChannelOpsAgent
from ..core.policy_engine import PolicyEngine
from ..enums import AutonomyMode, ChannelType


@pytest.mark.asyncio
async def test_agent_skips_when_off_or_shadow(db_session: AsyncSession):
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.OFF)
    result = await ChannelOpsAgent.run_cycle(db_session, ChannelType.SHOPEE)
    assert result["skipped"] is True and "OFF" in result["reason"]
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.SHADOW)
    result = await ChannelOpsAgent.run_cycle(db_session, ChannelType.SHOPEE)
    assert result["skipped"] is True and "SHADOW" in result["reason"]


@pytest.mark.asyncio
async def test_agent_polls_channel_in_full_mode(db_session: AsyncSession, monkeypatch):
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    seen = {"channel": None}

    async def _fake_poll(db, channel, since=None):
        seen["channel"] = channel
        return {"fetched": 2, "imported": 1, "reconcile": {"updated": 0, "skipped": 0}}

    monkeypatch.setattr(
        "graxia.packages.revenue_os.agents.channel_ops.poll_channel", _fake_poll)
    result = await ChannelOpsAgent.run_cycle(db_session, ChannelType.AMAZON)
    assert result["skipped"] is False
    assert seen["channel"] == ChannelType.AMAZON
    assert result["fetched"] == 2
