import pytest
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..celery.tasks.rollout_gate_checker import RolloutGateChecker
from ..core.policy_engine import PolicyEngine
from ..enums import AutonomyMode, IncidentSeverity
from ..models import AuditLog, IncidentEvent


@pytest.mark.asyncio
async def test_off_stage_requires_gate0(db_session: AsyncSession):
    readiness = await RolloutGateChecker.check_readiness(db_session)
    assert readiness["stage"] == AutonomyMode.OFF.value
    assert readiness["ready_for_next"] is False  # rules not seeded → blockers


@pytest.mark.asyncio
async def test_shadow_gate_blocks_on_high_incident(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.SHADOW)
    db_session.add(IncidentEvent(title="high", description="x", severity=IncidentSeverity.HIGH))
    for i in range(10):
        db_session.add(AuditLog(event_type="agent.price_change.shadow", message=f"shadow {i}"))
    await db_session.commit()
    readiness = await RolloutGateChecker.check_readiness(db_session)
    assert readiness["stage"] == AutonomyMode.SHADOW.value
    assert readiness["gates"]["no_high_incidents"] is False
    assert readiness["ready_for_next"] is False


@pytest.mark.asyncio
async def test_shadow_gate_ready_when_conditions_met(db_session: AsyncSession, monkeypatch):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.SHADOW)
    for i in range(10):
        db_session.add(AuditLog(event_type="agent.price_change.shadow", message=f"shadow {i}"))
    await db_session.commit()

    async def fake_days(db, mode):
        return 8

    monkeypatch.setattr(
        "graxia.packages.revenue_os.celery.tasks.rollout_gate_checker.days_in_mode",
        fake_days,
    )
    readiness = await RolloutGateChecker.check_readiness(db_session)
    assert readiness["gates"]["no_high_incidents"] is True
    assert readiness["gates"]["observation_period"] is True
    assert readiness["gates"]["shadow_decision_count"] is True
    assert readiness["ready_for_next"] is True
