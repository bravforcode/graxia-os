import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy_engine import PolicyEngine
from ..enums import ActionType, RuleType, ValueType
from ..models import PolicyRule
from ..schemas import PolicyRuleCreate


@pytest.mark.asyncio
async def test_seed_default_rules_idempotent(db_session: AsyncSession):
    first = await PolicyEngine.seed_default_rules(db_session)
    second = await PolicyEngine.seed_default_rules(db_session)
    assert first > 0
    assert second == 0


@pytest.mark.asyncio
async def test_create_rule(db_session: AsyncSession):
    payload = PolicyRuleCreate(
        action=ActionType.PRICE_CHANGE.value,
        rule_type=RuleType.MAX,
        value=10.0,
        description="tighter cap",
    )
    rule = PolicyRule(action=payload.action, rule_type=payload.rule_type,
                      value=payload.value, description=payload.description)
    db_session.add(rule)
    await db_session.commit()
    decision = await PolicyEngine.check(db_session, ActionType.PRICE_CHANGE, {"value": 15.0, "value_cents": 1000})
    assert decision.allow is False


@pytest.mark.asyncio
async def test_create_absolute_rule(db_session: AsyncSession):
    """Admin can configure an ABSOLUTE cap via the schema (draft-gap fix)."""
    payload = PolicyRuleCreate(
        action=ActionType.REFUND.value,
        rule_type=RuleType.MAX,
        value_type=ValueType.ABSOLUTE,
        value=500_00,
        description="tight absolute refund cap",
    )
    rule = PolicyRule(action=payload.action, rule_type=payload.rule_type,
                      value_type=payload.value_type, value=payload.value,
                      description=payload.description)
    db_session.add(rule)
    await db_session.commit()
    decision = await PolicyEngine.check(
        db_session, ActionType.REFUND, {"value": 10.0, "value_cents": 600_00}
    )
    assert decision.allow is False


@pytest.mark.asyncio
async def test_priority_highest_wins(db_session: AsyncSession):
    db_session.add(PolicyRule(action=ActionType.DISCOUNT.value, rule_type=RuleType.MAX,
                              value=5.0, priority=500))
    await db_session.commit()
    decision = await PolicyEngine.check(db_session, ActionType.DISCOUNT, {"value": 10.0, "value_cents": 1000})
    assert decision.allow is False
