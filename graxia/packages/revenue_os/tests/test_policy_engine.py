import uuid
from datetime import datetime, timedelta
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.policy_engine import PolicyEngine, PolicyDecision
from ..enums import ActionType, RuleType, ValueType, AutonomyMode, IncidentSeverity
from ..models import PolicyRule, AutonomyState, IncidentEvent


@pytest.mark.asyncio
async def test_fail_closed_when_no_rules(db_session: AsyncSession):
    decision = await PolicyEngine.check(db_session, ActionType.PRICE_CHANGE, {"value": 10.0, "value_cents": 1000})
    assert decision.allow is False
    assert "no policy rule" in decision.reason


@pytest.mark.asyncio
async def test_max_rule_denies_over_limit(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    decision = await PolicyEngine.check(db_session, ActionType.DISCOUNT, {"value": 25.0, "value_cents": 25000})
    assert decision.allow is False


@pytest.mark.asyncio
async def test_max_rule_allows_under_limit(db_session: AsyncSession):
    """Regression for Risk Audit #14: a MAX-only action under its cap MUST be allowed."""
    await PolicyEngine.seed_default_rules(db_session)
    decision = await PolicyEngine.check(db_session, ActionType.DISCOUNT, {"value": 10.0, "value_cents": 5000})
    assert decision.allow is True


@pytest.mark.asyncio
async def test_allow_rule_allows(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    decision = await PolicyEngine.check(db_session, ActionType.CAMPAIGN_PAUSE, {})
    assert decision.allow is True


@pytest.mark.asyncio
async def test_deny_rule_always_denies(db_session: AsyncSession):
    db_session.add(PolicyRule(action=ActionType.FULFILL.value, rule_type=RuleType.DENY,
                              description="test deny"))
    await db_session.commit()
    decision = await PolicyEngine.check(db_session, ActionType.FULFILL, {})
    assert decision.allow is False


@pytest.mark.asyncio
async def test_disabled_rule_ignored(db_session: AsyncSession):
    db_session.add(PolicyRule(action=ActionType.FULFILL.value, rule_type=RuleType.DENY,
                              enabled=False, description="disabled"))
    await db_session.commit()
    decision = await PolicyEngine.check(db_session, ActionType.FULFILL, {})
    assert decision.allow is False  # still fail-closed


@pytest.mark.asyncio
async def test_absolute_cap_denies_even_under_percent_cap(db_session: AsyncSession):
    """Risk Audit #9: 100% refund on a 50,000 THB order must be denied by the ABSOLUTE cap."""
    await PolicyEngine.seed_default_rules(db_session)
    decision = await PolicyEngine.check(
        db_session, ActionType.REFUND, {"value": 100.0, "value_cents": 50_000_00}
    )
    assert decision.allow is False
    assert "absolute" in decision.reason.lower() or "cents" in decision.reason.lower()


@pytest.mark.asyncio
async def test_new_row_defaults_to_autonomy_off(db_session: AsyncSession):
    """Risk Audit #1: a fresh singleton row must default to OFF, never FULL."""
    mode = await PolicyEngine.get_autonomy_mode(db_session)
    assert mode == AutonomyMode.OFF
    assert await PolicyEngine.is_autonomy_enabled(db_session) is False


@pytest.mark.asyncio
async def test_set_autonomy_mode_transitions(db_session: AsyncSession):
    for mode in (AutonomyMode.SHADOW, AutonomyMode.LIMITED, AutonomyMode.FULL, AutonomyMode.OFF):
        result = await PolicyEngine.set_autonomy_mode(db_session, mode)
        assert result == mode
        assert await PolicyEngine.get_autonomy_mode(db_session) == mode


@pytest.mark.asyncio
async def test_limited_mode_applies_multiplier(db_session: AsyncSession):
    """In LIMITED mode the MAX cap is value * limited_multiplier (0.25 by default)."""
    await PolicyEngine.seed_default_rules(db_session)  # DISCOUNT PERCENT MAX 15.0
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.LIMITED)
    # 5% is under the normal 15% cap but over 15% * 0.25 = 3.75%
    decision = await PolicyEngine.check(db_session, ActionType.DISCOUNT, {"value": 5.0, "value_cents": 1000})
    assert decision.allow is False


@pytest.mark.asyncio
async def test_circuit_breaker_trips_on_incident_spike(db_session: AsyncSession):
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    for i in range(5):
        db_session.add(IncidentEvent(title=f"synthetic {i}", description="test", severity=IncidentSeverity.MEDIUM))
    await db_session.commit()
    tripped = await PolicyEngine.check_circuit_breaker(db_session)
    assert tripped is True
    assert await PolicyEngine.get_autonomy_mode(db_session) == AutonomyMode.OFF


@pytest.mark.asyncio
async def test_circuit_breaker_does_not_trip_below_threshold(db_session: AsyncSession):
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    db_session.add(IncidentEvent(title="one incident", description="test", severity=IncidentSeverity.MEDIUM))
    await db_session.commit()
    tripped = await PolicyEngine.check_circuit_breaker(db_session)
    assert tripped is False
    assert await PolicyEngine.get_autonomy_mode(db_session) == AutonomyMode.FULL
