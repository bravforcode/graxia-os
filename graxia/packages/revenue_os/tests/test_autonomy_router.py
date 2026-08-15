import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy_engine import PolicyEngine
from ..enums import AutonomyMode
from ..models import AutonomyState


@pytest.mark.asyncio
async def test_set_autonomy_mode_creates_state_row(db_session: AsyncSession):
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.SHADOW)
    state = await db_session.scalar(select(AutonomyState).where(AutonomyState.id == 1))
    assert state is not None
    assert state.mode == AutonomyMode.SHADOW


@pytest.mark.asyncio
async def test_set_autonomy_mode_transitions_all_four(db_session: AsyncSession):
    for mode in (AutonomyMode.OFF, AutonomyMode.SHADOW, AutonomyMode.LIMITED, AutonomyMode.FULL):
        await PolicyEngine.set_autonomy_mode(db_session, mode)
        assert await PolicyEngine.get_autonomy_mode(db_session) == mode


@pytest.mark.asyncio
async def test_agents_skip_when_mode_off(db_session: AsyncSession):
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.OFF)
    from ..agents.commerce_ops import CommerceOpsAgent
    result = await CommerceOpsAgent.run_cycle(db_session)
    assert result["skipped"] is True
