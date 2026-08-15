"""Policy rule admin API - agents cannot modify rules."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.core.policy_engine import PolicyEngine
from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.models import PolicyRule
from ....packages.revenue_os.schemas import PolicyRuleCreate, PolicyRuleResponse, PolicyRuleUpdate
from ..dependencies import require_admin_api_key

router = APIRouter(dependencies=[Depends(require_admin_api_key)])


@router.get("/rules", response_model=list[PolicyRuleResponse])
async def list_rules(db: AsyncSession = Depends(get_db)) -> list[PolicyRule]:
    result = await db.execute(select(PolicyRule).order_by(PolicyRule.action, PolicyRule.priority.desc()))
    return list(result.scalars().all())


@router.post("/rules", response_model=PolicyRuleResponse)
async def create_rule(body: PolicyRuleCreate, db: AsyncSession = Depends(get_db)) -> PolicyRule:
    rule = PolicyRule(**body.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.patch("/rules/{rule_id}", response_model=PolicyRuleResponse)
async def update_rule(rule_id: UUID, body: PolicyRuleUpdate, db: AsyncSession = Depends(get_db)) -> PolicyRule:
    rule = await db.get(PolicyRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    rule = await db.get(PolicyRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    await db.delete(rule)
    await db.commit()


@router.post("/seed")
async def seed_rules(db: AsyncSession = Depends(get_db)) -> dict:
    inserted = await PolicyEngine.seed_default_rules(db)
    return {"inserted": inserted}
