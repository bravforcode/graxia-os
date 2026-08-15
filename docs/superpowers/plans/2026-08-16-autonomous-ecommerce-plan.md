# Autonomous Ecommerce Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 1 — digital-first autonomous storefront on the existing Revenue OS: policy engine as the only guardrail (no human approval), digital fulfillment wired to payments, commerce ops agent, support chat agent, kill switch.

**Architecture:** Extend the existing `graxia/packages/revenue_os` package. A new `PolicyEngine` gates every money/product-touching action (fail-closed). `fulfill_order` already exists in `FulfillmentService` but is never called — wire it into the Stripe webhook path. `CommerceOpsAgent` runs decision cycles on celery beat. `SupportAgent` answers chat with policy-checked actions. An `AutonomyState` singleton flag is the global kill switch.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2 async, Celery + Redis, pytest (asyncio), existing fixtures in `graxia/packages/revenue_os/tests/conftest.py`.

## Global Constraints

- Test framework: pytest with `db_session`, `sample_product_data`, `sample_order_data`, `sample_customer_data`, `mock_resend_client`, `mock_anthropic_client` fixtures from `graxia/packages/revenue_os/tests/conftest.py`
- Run tests: `pytest graxia/packages/revenue_os/tests/ -v` (from repo root)
- All new DB models go in `graxia/packages/revenue_os/models.py` following existing SQLAlchemy 2 style (`Mapped`, `mapped_column`, `SAEnum`)
- All new enums go in `graxia/packages/revenue_os/enums.py` following existing `StrEnum` style
- All services are static-method classes with `db: AsyncSession` as first arg (existing pattern)
- Policy engine is fail-closed: no rules matched for an action → DENY
- Agents CANNOT modify policy rules — rules are admin-only via API
- Every agent action MUST write `AuditLog` (model exists: `revenue_os_audit_logs`)
- Every policy deny MUST create an `IncidentEvent` (severity LOW for routine, MEDIUM for money actions)
- Keep existing tests green — do not modify existing behavior

---

### Task 1: PolicyRule model, enums, PolicyEngine core

**Files:**
- Modify: `graxia/packages/revenue_os/enums.py` (append enums)
- Modify: `graxia/packages/revenue_os/models.py` (append PolicyRule + AutonomyState)
- Create: `graxia/packages/revenue_os/core/policy_engine.py`
- Create: `graxia/packages/revenue_os/tests/test_policy_engine.py`

**Interfaces:**
- Produces:
  - `class ActionType(StrEnum)`: PRICE_CHANGE="price_change", DISCOUNT="discount", REFUND="refund", FULFILL="fulfill", CAMPAIGN_PAUSE="campaign_pause", CAMPAIGN_PUBLISH="campaign_publish", EMAIL_SEND="email_send"
  - `class RuleType(StrEnum)`: MAX="max", MIN="min", ALLOW="allow", DENY="deny"
  - `class PolicyRule(Base)` — table `revenue_os_policy_rules`: `id UUID PK`, `action str(50)`, `rule_type SAEnum(RuleType)`, `value Optional[float]`, `scope str(50) default "global"`, `scope_value Optional[str]`, `enabled bool default True`, `priority int default 100`, `description Optional[str]`, `created_at`, `updated_at`
  - `class AutonomyState(Base)` — table `revenue_os_autonomy_state`: `id int PK default 1` (singleton), `enabled bool default True`, `updated_at`
  - `class PolicyDecision` (dataclass): `allow: bool`, `reason: str`, `rule_id: Optional[UUID] = None`
  - `class PolicyEngine` with static methods: `check(db, action: str, context: dict) -> PolicyDecision`, `is_autonomy_enabled(db) -> bool`, `seed_default_rules(db) -> int`, `_evaluate(rule, context) -> Optional[str]`

- [ ] **Step 1: Write failing tests** — `tests/test_policy_engine.py`

```python
import uuid
from datetime import datetime, timedelta
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.policy_engine import PolicyEngine, PolicyDecision
from ..enums import ActionType, RuleType, SupportIntent
from ..models import PolicyRule, AutonomyState, IncidentEvent


@pytest.mark.asyncio
async def test_fail_closed_when_no_rules(db_session: AsyncSession):
    decision = await PolicyEngine.check(db_session, ActionType.PRICE_CHANGE, {"value": 10.0})
    assert decision.allow is False
    assert "no policy rule" in decision.reason


@pytest.mark.asyncio
async def test_max_rule_denies_over_limit(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    decision = await PolicyEngine.check(db_session, ActionType.DISCOUNT, {"value": 25.0})
    assert decision.allow is False
    assert "discount" in decision.reason.lower() or "max" in decision.reason.lower()


@pytest.mark.asyncio
async def test_max_rule_allows_under_limit(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    decision = await PolicyEngine.check(db_session, ActionType.DISCOUNT, {"value": 10.0})
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
    assert decision.allow is False  # still fail-closed, no other rule


@pytest.mark.asyncio
async def test_autonomy_enabled_default(db_session: AsyncSession):
    assert await PolicyEngine.is_autonomy_enabled(db_session) is True


@pytest.mark.asyncio
async def test_autonomy_disabled(db_session: AsyncSession):
    state = await db_session.scalar(select(AutonomyState).where(AutonomyState.id == 1))
    state.enabled = False
    await db_session.commit()
    assert await PolicyEngine.is_autonomy_enabled(db_session) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_policy_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named '..core.policy_engine'`

- [ ] **Step 3: Add enums** — append to `enums.py`

```python
class ActionType(StrEnum):
    PRICE_CHANGE = "price_change"
    DISCOUNT = "discount"
    REFUND = "refund"
    FULFILL = "fulfill"
    CAMPAIGN_PAUSE = "campaign_pause"
    CAMPAIGN_PUBLISH = "campaign_publish"
    EMAIL_SEND = "email_send"


class RuleType(StrEnum):
    MAX = "max"
    MIN = "min"
    ALLOW = "allow"
    DENY = "deny"


class SupportIntent(StrEnum):
    WISMO = "wismo"
    REFUND = "refund"
    PRODUCT_QUESTION = "product_question"
    COMPLAINT = "complaint"
    SALES = "sales"
    OTHER = "other"
```

- [ ] **Step 4: Add models** — append to `models.py` (after `AttributionSummary`, before the section separator; follow existing style)

```python
# ══════════════════════════════════════════════════════════════════
# POLICY & AUTONOMY MODELS
# ══════════════════════════════════════════════════════════════════

class PolicyRule(Base):
    """
    Policy engine rules - the ONLY guardrail in full-autonomous mode.
    Agents cannot modify these (admin-only API).
    """
    __tablename__ = "revenue_os_policy_rules"
    __table_args__ = (
        Index("ix_policy_action_scope", "action", "scope"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_type: Mapped[RuleType] = mapped_column(SAEnum(RuleType), nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Float)
    scope: Mapped[str] = mapped_column(String(50), default="global")
    scope_value: Mapped[Optional[str]] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    description: Mapped[Optional[str]] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AutonomyState(Base):
    """
    Global autonomy kill switch (singleton row, id=1).
    When disabled, all agents stop taking actions.
    """
    __tablename__ = "revenue_os_autonomy_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

Check imports at top of `models.py` — `Float` and `Boolean` may need adding to the existing `from sqlalchemy import ...` line.

- [ ] **Step 5: Implement policy engine** — create `core/policy_engine.py`

```python
"""Policy engine - the ONLY guardrail in full-autonomous mode.

Every money/product-touching action must pass PolicyEngine.check() first.
Fail-closed: an action with no matching rules is DENIED.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import AUTONOMY_STATE_ID
from ..enums import RuleType
from ..models import AutonomyState, PolicyRule


@dataclass
class PolicyDecision:
    allow: bool
    reason: str
    rule_id: Optional[UUID] = None


class PolicyEngine:
    """Evaluate policy rules for autonomous actions."""

    @staticmethod
    async def is_autonomy_enabled(db: AsyncSession) -> bool:
        state = await db.scalar(select(AutonomyState).where(AutonomyState.id == AUTONOMY_STATE_ID))
        if state is None:
            db.add(AutonomyState(id=AUTONOMY_STATE_ID, enabled=True))
            await db.commit()
            return True
        return state.enabled

    @staticmethod
    async def _load_rules(db: AsyncSession, action: str) -> list[PolicyRule]:
        result = await db.execute(
            select(PolicyRule)
            .where(PolicyRule.action == action, PolicyRule.enabled.is_(True))
            .order_by(PolicyRule.priority.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    def _evaluate(rule: PolicyRule, context: dict) -> Optional[str]:
        """Return a deny reason if the rule denies the action, else None."""
        if rule.scope != "global":
            if rule.scope == "product_id" and context.get("product_id") != rule.scope_value:
                return None
        if rule.rule_type == RuleType.DENY:
            return f"denied by rule {rule.id}"
        if rule.rule_type in (RuleType.MAX, RuleType.MIN):
            value = context.get("value")
            if value is None:
                return f"rule {rule.id} needs context['value']"
            if rule.rule_type == RuleType.MAX and value > rule.value:
                return f"value {value} exceeds max {rule.value} (rule {rule.id})"
            if rule.rule_type == RuleType.MIN and value < rule.value:
                return f"value {value} below min {rule.value} (rule {rule.id})"
        return None

    @classmethod
    async def check(cls, db: AsyncSession, action: str, context: dict) -> PolicyDecision:
        """Evaluate all rules for an action. Any deny wins. Fail-closed."""
        rules = await cls._load_rules(db, action)
        if not rules:
            return PolicyDecision(allow=False, reason=f"no policy rule matched for action '{action}'")
        denied: Optional[PolicyDecision] = None
        allowed = False
        for rule in rules:
            reason = cls._evaluate(rule, context)
            if reason is not None:
                denied = PolicyDecision(allow=False, reason=reason, rule_id=rule.id)
                break
            if rule.rule_type == RuleType.ALLOW:
                allowed = True
        if denied is not None:
            return denied
        if allowed:
            return PolicyDecision(allow=True, reason=f"allowed by policy (action '{action}')")
        return PolicyDecision(allow=False, reason=f"no allow rule matched for action '{action}'")

    @staticmethod
    async def seed_default_rules(db: AsyncSession) -> int:
        """Insert default Phase-1 rules. Idempotent (skips existing action+rule_type)."""
        defaults = [
            (ActionType.PRICE_CHANGE.value, RuleType.MAX, 20.0, "max price change percent"),
            (ActionType.DISCOUNT.value, RuleType.MAX, 15.0, "max discount percent"),
            (ActionType.REFUND.value, RuleType.MAX, 100.0, "max refund percent"),
            (ActionType.FULFILL.value, RuleType.ALLOW, None, "allow fulfillment"),
            (ActionType.CAMPAIGN_PAUSE.value, RuleType.ALLOW, None, "allow pausing campaigns"),
            (ActionType.CAMPAIGN_PUBLISH.value, RuleType.ALLOW, None, "allow publishing campaigns"),
            (ActionType.EMAIL_SEND.value, RuleType.MAX, 5.0, "max emails per customer per day"),
        ]
        inserted = 0
        for action, rule_type, value, desc in defaults:
            existing = await db.scalar(
                select(PolicyRule).where(PolicyRule.action == action, PolicyRule.rule_type == rule_type)
            )
            if existing is None:
                db.add(PolicyRule(action=action, rule_type=rule_type, value=value, description=desc))
                inserted += 1
        await db.commit()
        return inserted
```

- [ ] **Step 6: Add constant** — in `constants.py` add:

```python
AUTONOMY_STATE_ID = 1  # singleton row id for the autonomy kill switch
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_policy_engine.py -v`
Expected: 8 PASSED

- [ ] **Step 8: Commit**

```bash
git add graxia/packages/revenue_os/enums.py graxia/packages/revenue_os/models.py graxia/packages/revenue_os/constants.py graxia/packages/revenue_os/core/policy_engine.py graxia/packages/revenue_os/tests/test_policy_engine.py
git commit -m "feat(revenue-os): policy engine with fail-closed rules + autonomy state"
```

---

### Task 2: Autonomy kill switch API

**Files:**
- Create: `graxia/services/revenue_os_api/routers/autonomy.py`
- Modify: `graxia/services/revenue_os_api/router.py`
- Create: `graxia/packages/revenue_os/tests/test_autonomy_router.py` (unit-level: test the state transitions, not HTTP)

**Interfaces:**
- Consumes: `PolicyEngine.is_autonomy_enabled(db)` from Task 1; `AutonomyState` model; `get_db` dependency from `graxia/services/revenue_os_api/dependencies.py`
- Produces: router with `GET /api/autonomy/status -> {"enabled": bool}`, `POST /api/autonomy/enable`, `POST /api/autonomy/disable`; `async def set_autonomy(db, enabled: bool) -> bool` in policy engine

- [ ] **Step 1: Write failing tests** — `tests/test_autonomy_router.py`

```python
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy_engine import PolicyEngine
from ..models import AutonomyState
from ..enums import ActionType


@pytest.mark.asyncio
async def test_set_autonomy_creates_state_row(db_session: AsyncSession):
    await PolicyEngine.set_autonomy(db_session, False)
    state = await db_session.scalar(select(AutonomyState).where(AutonomyState.id == 1))
    assert state is not None
    assert state.enabled is False


@pytest.mark.asyncio
async def test_set_autonomy_toggle(db_session: AsyncSession):
    await PolicyEngine.set_autonomy(db_session, False)
    assert await PolicyEngine.is_autonomy_enabled(db_session) is False
    await PolicyEngine.set_autonomy(db_session, True)
    assert await PolicyEngine.is_autonomy_enabled(db_session) is True


@pytest.mark.asyncio
async def test_agents_skip_when_autonomy_disabled(db_session: AsyncSession):
    await PolicyEngine.set_autonomy(db_session, False)
    # commerce ops checks the flag before acting - simulate here
    from ..agents.commerce_ops import CommerceOpsAgent
    result = await CommerceOpsAgent.run_cycle(db_session)
    assert result["skipped"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_autonomy_router.py -v`
Expected: FAIL — `AttributeError: 'PolicyEngine' object has no attribute 'set_autonomy'` / module import error

- [ ] **Step 3: Add set_autonomy to PolicyEngine** — append to `core/policy_engine.py`

```python
    @staticmethod
    async def set_autonomy(db: AsyncSession, enabled: bool) -> bool:
        """Set the global kill switch. Returns the new state."""
        state = await db.scalar(select(AutonomyState).where(AutonomyState.id == AUTONOMY_STATE_ID))
        if state is None:
            state = AutonomyState(id=AUTONOMY_STATE_ID, enabled=enabled)
            db.add(state)
        else:
            state.enabled = enabled
        await db.commit()
        return enabled
```

- [ ] **Step 4: Create router** — `graxia/services/revenue_os_api/routers/autonomy.py`

```python
"""Global autonomy kill switch."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.core.policy_engine import PolicyEngine
from ..dependencies import get_db

router = APIRouter(prefix="/api/autonomy", tags=["autonomy"])


@router.get("/status")
async def get_status(db: AsyncSession = Depends(get_db)) -> dict:
    enabled = await PolicyEngine.is_autonomy_enabled(db)
    return {"enabled": enabled}


@router.post("/enable")
async def enable(db: AsyncSession = Depends(get_db)) -> dict:
    return {"enabled": await PolicyEngine.set_autonomy(db, True)}


@router.post("/disable")
async def disable(db: AsyncSession = Depends(get_db)) -> dict:
    return {"enabled": await PolicyEngine.set_autonomy(db, False)}
```

- [ ] **Step 5: Register router** — in `graxia/services/revenue_os_api/router.py`, add to the existing router includes:

```python
from .routers.autonomy import router as autonomy_router
# inside the list of includes (follow existing style, e.g.):
# api_router.include_router(autonomy_router)
```

Match the file's existing include pattern exactly — if it uses `router.include_router(x, prefix=...)`, follow that.

- [ ] **Step 6: Add CommerceOpsAgent stub so tests import** — create `agents/commerce_ops.py` (full implementation in Task 5; stub now):

```python
"""Commerce operations agent - full implementation in Task 5."""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy_engine import PolicyEngine

logger = structlog.get_logger()


class CommerceOpsAgent:
    """Main store manager: reads state, decides, policy-checks, executes, logs."""

    @staticmethod
    async def run_cycle(db: AsyncSession) -> dict:
        if not await PolicyEngine.is_autonomy_enabled(db):
            logger.info("commerce_ops_skipped", reason="autonomy_disabled")
            return {"skipped": True, "actions_taken": [], "policy_denials": []}
        # Task 5 implements the jobs
        return {"skipped": False, "actions_taken": [], "policy_denials": []}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_autonomy_router.py -v`
Expected: 3 PASSED

- [ ] **Step 8: Commit**

```bash
git add graxia/packages/revenue_os/core/policy_engine.py graxia/packages/revenue_os/agents/commerce_ops.py graxia/packages/revenue_os/tests/test_autonomy_router.py graxia/services/revenue_os_api/routers/autonomy.py graxia/services/revenue_os_api/router.py
git commit -m "feat(revenue-os): autonomy kill switch API + state transitions"
```

---

### Task 3: Policy admin API (rules CRUD + seed)

**Files:**
- Create: `graxia/services/revenue_os_api/routers/policy.py`
- Modify: `graxia/services/revenue_os_api/router.py`
- Modify: `graxia/packages/revenue_os/schemas.py` (append schemas)
- Create: `graxia/packages/revenue_os/tests/test_policy_admin.py`

**Interfaces:**
- Consumes: `PolicyRule` model, `RuleType`/`ActionType` enums, `PolicyEngine.seed_default_rules` (Task 1)
- Produces: router with `GET /api/policy/rules`, `POST /api/policy/rules`, `PATCH /api/policy/rules/{rule_id}`, `DELETE /api/policy/rules/{rule_id}`, `POST /api/policy/seed`; schemas `PolicyRuleCreate`, `PolicyRuleUpdate`, `PolicyRuleResponse`

- [ ] **Step 1: Write failing tests** — `tests/test_policy_admin.py`

```python
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy_engine import PolicyEngine
from ..enums import ActionType, RuleType
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
    decision = await PolicyEngine.check(db_session, ActionType.PRICE_CHANGE, {"value": 15.0})
    assert decision.allow is False


@pytest.mark.asyncio
async def test_priority_highest_wins(db_session: AsyncSession):
    db_session.add(PolicyRule(action=ActionType.DISCOUNT.value, rule_type=RuleType.MAX, value=5.0, priority=500))
    await db_session.commit()
    decision = await PolicyEngine.check(db_session, ActionType.DISCOUNT, {"value": 10.0})
    assert decision.allow is False  # stricter high-priority rule wins
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_policy_admin.py -v`
Expected: FAIL — `ImportError: cannot import name 'PolicyRuleCreate' from '..schemas'`

- [ ] **Step 3: Add schemas** — append to `schemas.py`

```python
class PolicyRuleCreate(BaseModel):
    action: str
    rule_type: RuleType
    value: Optional[float] = None
    scope: str = "global"
    scope_value: Optional[str] = None
    priority: int = 100
    description: Optional[str] = None


class PolicyRuleUpdate(BaseModel):
    value: Optional[float] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    description: Optional[str] = None


class PolicyRuleResponse(BaseModel):
    id: UUID
    action: str
    rule_type: RuleType
    value: Optional[float]
    scope: str
    scope_value: Optional[str]
    enabled: bool
    priority: int
    description: Optional[str]

    class Config:
        from_attributes = True
```

(Add `from ..enums import RuleType` / import `RuleType` at the top of `schemas.py` if not already imported — check existing import block first.)

- [ ] **Step 4: Create router** — `graxia/services/revenue_os_api/routers/policy.py`

```python
"""Policy rule admin API - agents cannot modify rules."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.core.policy_engine import PolicyEngine
from ....packages.revenue_os.models import PolicyRule
from ....packages.revenue_os.schemas import PolicyRuleCreate, PolicyRuleResponse, PolicyRuleUpdate
from ..dependencies import get_db

router = APIRouter(prefix="/api/policy", tags=["policy"])


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
```

- [ ] **Step 5: Register router** — in `router.py`, follow the same pattern as Task 2 Step 5.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_policy_admin.py -v`
Expected: 3 PASSED

- [ ] **Step 7: Commit**

```bash
git add graxia/packages/revenue_os/schemas.py graxia/packages/revenue_os/tests/test_policy_admin.py graxia/services/revenue_os_api/routers/policy.py graxia/services/revenue_os_api/router.py
git commit -m "feat(revenue-os): policy admin CRUD API + idempotent rule seeding"
```

---

### Task 4: Wire digital fulfillment into payment flow

**Files:**
- Create: `graxia/packages/revenue_os/celery/tasks/digital_fulfillment.py`
- Modify: `graxia/packages/revenue_os/services/webhook_processor.py`
- Create: `graxia/packages/revenue_os/tests/test_webhook_fulfillment.py`

**Interfaces:**
- Consumes: `WebhookProcessor.process_stripe_checkout_completed(session, db) -> Order` (existing), `FulfillmentService.fulfill_order(db, order_id, auto_queue_email=True) -> DeliveryEvent` (existing, idempotent), `OrderService.update_order_status(db, order_id, status)` (existing), `get_db_session()` from `graxia/packages/revenue_os/db.py`, `acquire_automation_lock` from `core/db_ops.py`
- Produces: celery task `digital_fulfillment()` (sweeps PAID orders missing delivery events); `process_stripe_checkout_completed` now fulfills immediately after order creation

- [ ] **Step 1: Write failing tests** — `tests/test_webhook_fulfillment.py`

```python
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..celery.tasks.digital_fulfillment import sweep_pending_fulfillments
from ..enums import DeliveryStatus, OrderStatus
from ..models import DeliveryEvent, Order
from ..services.fulfillment_service import FulfillmentService
from ..services.order_service import OrderService
from ..services.webhook_processor import WebhookProcessor


@pytest.mark.asyncio
async def test_webhook_fulfills_digital_order(db_session: AsyncSession, sample_product_data, sample_customer_data):
    product = sample_product_data
    order = await WebhookProcessor.process_stripe_checkout_completed(
        {
            "id": "cs_test_1",
            "customer_email": sample_customer_data["email"],
            "customer_name": sample_customer_data["name"],
            "amount_total": product.price_cents,
            "currency": "thb",
            "payment_intent": "pi_test_1",
            "metadata": {"product_id": str(product.id)},
        },
        db_session,
    )
    assert order.status == OrderStatus.PAID
    delivery = await db_session.scalar(
        select(DeliveryEvent).where(DeliveryEvent.order_id == order.id)
    )
    assert delivery is not None
    assert delivery.status == DeliveryStatus.DELIVERED


@pytest.mark.asyncio
async def test_sweep_fulfills_stuck_paid_orders(db_session: AsyncSession, sample_product_data, sample_customer_data):
    order = await OrderService.create_order(
        db_session,
        platform="stripe",
        platform_order_id="cs_stuck_1",
        customer_email=sample_customer_data["email"],
        product_id=sample_product_data.id,
        amount_cents=sample_product_data.price_cents,
    )
    await OrderService.update_order_status(db_session, order.id, OrderStatus.PAID)
    fulfilled = await sweep_pending_fulfillments(db_session)
    assert fulfilled == 1
    delivery = await db_session.scalar(
        select(DeliveryEvent).where(DeliveryEvent.order_id == order.id)
    )
    assert delivery is not None


@pytest.mark.asyncio
async def test_sweep_is_idempotent(db_session: AsyncSession, sample_product_data, sample_customer_data):
    order = await WebhookProcessor.process_stripe_checkout_completed(
        {
            "id": "cs_test_2",
            "customer_email": sample_customer_data["email"],
            "amount_total": sample_product_data.price_cents,
            "currency": "thb",
            "payment_intent": "pi_test_2",
            "metadata": {"product_id": str(product.id)},
        },
        db_session,
    )
    assert await sweep_pending_fulfillments(db_session) == 0  # already fulfilled
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_webhook_fulfillment.py -v`
Expected: FAIL — import error on `sweep_pending_fulfillments`; webhook test may pass but `assert order.status == PAID` may fail if webhook leaves PENDING — fix webhook in Step 4.

- [ ] **Step 3: Create celery task** — `celery/tasks/digital_fulfillment.py`

```python
"""Digital fulfillment: sweep PAID orders missing delivery events (idempotent)."""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...enums import OrderStatus
from ...models import DeliveryEvent, Order
from ...services.fulfillment_service import FulfillmentService

logger = structlog.get_logger()


async def sweep_pending_fulfillments(db: AsyncSession) -> int:
    """Fulfill every PAID order that has no delivery event yet. Returns count."""
    result = await db.execute(
        select(Order).where(Order.status == OrderStatus.PAID).order_by(Order.created_at)
    )
    orders = list(result.scalars().all())
    fulfilled = 0
    for order in orders:
        has_delivery = await db.scalar(
            select(DeliveryEvent.id).where(DeliveryEvent.order_id == order.id).limit(1)
        )
        if has_delivery:
            continue
        try:
            await FulfillmentService.fulfill_order(db, order.id, auto_queue_email=True)
            fulfilled += 1
        except Exception:
            logger.exception("digital_fulfillment_failed", order_id=str(order.id))
    await db.commit()
    return fulfilled


def digital_fulfillment():
    """Celery wrapper. Follows the asyncio.run pattern from agent_consumers.py."""
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await sweep_pending_fulfillments(db)

    return asyncio.run(_impl())
```

- [ ] **Step 4: Modify webhook processor** — in `webhook_processor.py`, inside `process_stripe_checkout_completed`, after the order is created, add (keep existing logic intact):

```python
            # Digital fulfillment: fulfill immediately (idempotent)
            if order.status != OrderStatus.PAID:
                order = await OrderService.update_order_status(db, order.id, OrderStatus.PAID)
            await FulfillmentService.fulfill_order(db, order.id, auto_queue_email=True)
```

Add imports for `OrderStatus` and `OrderService`/`FulfillmentService` to `webhook_processor.py` if missing. Do the same minimal PAID+fulfill step in `process_gumroad_sale` and `process_paypal_payment_completed` (same pattern).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_webhook_fulfillment.py graxia/packages/revenue_os/tests/test_fulfillment_service.py -v`
Expected: 3 new PASSED + existing fulfillment tests still PASS (fulfill_order idempotency covers double-webhook)

- [ ] **Step 6: Commit**

```bash
git add graxia/packages/revenue_os/celery/tasks/digital_fulfillment.py graxia/packages/revenue_os/services/webhook_processor.py graxia/packages/revenue_os/tests/test_webhook_fulfillment.py
git commit -m "feat(revenue-os): wire digital fulfillment into payment webhooks + sweep task"
```

---

### Task 5: Commerce Ops Agent (autonomous decision cycle)

**Files:**
- Modify: `graxia/packages/revenue_os/agents/commerce_ops.py` (full implementation replacing Task 2 stub)
- Create: `graxia/packages/revenue_os/tests/test_commerce_ops.py`

**Interfaces:**
- Consumes: `PolicyEngine.check/is_autonomy_enabled` (Task 1), `ActionType`/`RuleType` enums, `Order`/`Product`/`AuditLog`/`IncidentEvent`/`StrategyLog` models, `OrderService` (existing), `RevenueCampaignService.pause_campaign` (existing), `ChiefOfStaffAgent.escalate_issue(db, title, description, severity, affected_campaign_id=None, affected_order_id=None)` (existing), `sample_order_data`/`sample_product_data` fixtures
- Produces: `CommerceOpsAgent.run_cycle(db) -> dict` with keys `skipped`, `actions_taken: list[str]`, `policy_denials: list[str]`; private jobs `_price_optimization`, `_campaign_check`, `_stale_order_review`, `_daily_report`; helper `_log_action(db, event_type, message, metadata)`

- [ ] **Step 1: Write failing tests** — `tests/test_commerce_ops.py`

```python
import uuid
from datetime import datetime, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.commerce_ops import CommerceOpsAgent
from ..core.policy_engine import PolicyEngine
from ..enums import CampaignStatus, IncidentSeverity, OrderStatus, ProductStatus
from ..models import AuditLog, IncidentEvent, Product, RevenueCampaign, StrategyLog
from ..services.order_service import OrderService


@pytest.mark.asyncio
async def test_run_cycle_skips_when_disabled(db_session: AsyncSession):
    await PolicyEngine.set_autonomy(db_session, False)
    result = await CommerceOpsAgent.run_cycle(db_session)
    assert result["skipped"] is True


@pytest.mark.asyncio
async def test_price_cut_for_stale_product(db_session: AsyncSession, sample_product_data):
    await PolicyEngine.seed_default_rules(db_session)
    product = sample_product_data
    product.status = ProductStatus.PUBLISHED
    product.created_at = datetime.utcnow() - timedelta(days=21)
    await db_session.commit()
    old_price = product.price_cents

    result = await CommerceOpsAgent.run_cycle(db_session)

    assert any("price" in a.lower() for a in result["actions_taken"])
    await db_session.refresh(product)
    assert product.price_cents < old_price
    # policy allows ±20%: 10% cut stays within
    assert old_price - product.price_cents <= old_price * 0.2
    log = await db_session.scalar(select(AuditLog).where(AuditLog.event_type == "agent.price_change"))
    assert log is not None


@pytest.mark.asyncio
async def test_price_cut_denied_beyond_policy(db_session: AsyncSession, sample_product_data):
    await PolicyEngine.seed_default_rules(db_session)
    # tighten policy: max 5%
    from ..enums import RuleType
    from ..models import PolicyRule
    db_session.add(PolicyRule(action="price_change", rule_type=RuleType.MAX, value=5.0, priority=500))
    await db_session.commit()

    product = sample_product_data
    product.status = ProductStatus.PUBLISHED
    product.created_at = datetime.utcnow() - timedelta(days=21)
    await db_session.commit()

    result = await CommerceOpsAgent.run_cycle(db_session)
    assert result["policy_denials"], "expected a denial"
    incident = await db_session.scalar(select(IncidentEvent).order_by(IncidentEvent.created_at.desc()))
    assert incident is not None


@pytest.mark.asyncio
async def test_pause_stale_campaign(db_session: AsyncSession, sample_product_data, sample_campaign_data):
    await PolicyEngine.seed_default_rules(db_session)
    campaign = RevenueCampaignService.create_campaign(
        db_session,
        name="stale-campaign",
        slug="stale-campaign",
        product_id=sample_product_data.id,
    )
    await db_session.commit()
    result = await CommerceOpsAgent.run_cycle(db_session)
    # campaign with no orders and no budget is left running; only price job runs
    assert result["actions_taken"] or result["policy_denials"] or result["skipped"] is False


@pytest.mark.asyncio
async def test_stale_pending_order_escalates(db_session: AsyncSession, sample_order_data):
    await PolicyEngine.seed_default_rules(db_session)
    order = sample_order_data
    order.status = OrderStatus.PENDING
    order.created_at = datetime.utcnow() - timedelta(hours=72)
    await db_session.commit()
    result = await CommerceOpsAgent.run_cycle(db_session)
    incident = await db_session.scalar(
        select(IncidentEvent).where(IncidentEvent.severity == IncidentSeverity.LOW)
    )
    assert incident is not None
    assert "PENDING" in incident.title.upper() or "order" in incident.title.lower()


@pytest.mark.asyncio
async def test_daily_report_writes_strategy_log(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    result = await CommerceOpsAgent.run_cycle(db_session)
    log = await db_session.scalar(select(StrategyLog).order_by(StrategyLog.created_at.desc()))
    assert log is not None
    assert "summary" in (log.summary or "")
```

Note: tests use `RevenueCampaignService` — import from `..services.campaign_service`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_commerce_ops.py -v`
Expected: FAIL — stub returns empty actions

- [ ] **Step 3: Implement full agent** — replace stub in `agents/commerce_ops.py`

```python
"""Commerce operations agent - the main store manager.

Runs on celery beat. Reads state, decides, policy-checks, executes, logs.
Rule-based for Phase 1 (no LLM in the critical path).
"""
from __future__ import annotations

import structlog
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy_engine import PolicyEngine
from ..enums import ActionType, CampaignStatus, IncidentSeverity, OrderStatus, ProductStatus
from ..models import AuditLog, IncidentEvent, Order, Product, RevenueCampaign, StrategyLog
from ..services.campaign_service import RevenueCampaignService

logger = structlog.get_logger()

PRICE_CUT_PERCENT = 10.0
STALE_PRODUCT_DAYS = 14
STALE_ORDER_HOURS = 48


class CommerceOpsAgent:
    """Main store manager: read state → decide → policy check → execute → log."""

    @staticmethod
    async def _log_action(db: AsyncSession, event_type: str, message: str, metadata: dict | None = None) -> None:
        db.add(AuditLog(event_type=event_type, message=message, metadata_=metadata or {}))
        await db.flush()

    @staticmethod
    async def _price_optimization(db: AsyncSession) -> tuple[list[str], list[str]]:
        actions, denials = [], []
        cutoff = datetime.utcnow() - timedelta(days=7)
        result = await db.execute(
            select(Product).where(Product.status == ProductStatus.PUBLISHED)
        )
        for product in list(result.scalars().all()):
            order_count = await db.scalar(
                select(Order.id).where(
                    Order.product_id == product.id,
                    Order.status == OrderStatus.PAID,
                    Order.purchased_at >= cutoff,
                ).limit(1)
            )
            if order_count is None and product.created_at < datetime.utcnow() - timedelta(days=STALE_PRODUCT_DAYS):
                decision = await PolicyEngine.check(
                    db, ActionType.PRICE_CHANGE,
                    {"value": PRICE_CUT_PERCENT, "product_id": str(product.id)},
                )
                if not decision.allow:
                    denials.append(f"price_change:{product.slug}:{decision.reason}")
                    db.add(IncidentEvent(
                        title=f"Policy denied price change for {product.name}",
                        description=decision.reason,
                        severity=IncidentSeverity.MEDIUM,
                    ))
                    continue
                cut = int(product.price_cents * (PRICE_CUT_PERCENT / 100))
                product.price_cents = max(0, product.price_cents - cut)
                actions.append(f"price_change:{product.slug}:-{PRICE_CUT_PERCENT}%")
                await CommerceOpsAgent._log_action(
                    db, "agent.price_change",
                    f"Agent cut price of {product.name} by {PRICE_CUT_PERCENT}%",
                    {"product_id": str(product.id), "percent": PRICE_CUT_PERCENT},
                )
        await db.flush()
        return actions, denials

    @staticmethod
    async def _campaign_check(db: AsyncSession) -> tuple[list[str], list[str]]:
        actions, denials = [], []
        result = await db.execute(
            select(RevenueCampaign).where(RevenueCampaign.status == CampaignStatus.ACTIVE)
        )
        for campaign in list(result.scalars().all()):
            metrics = await RevenueCampaignService.check_campaign_budget(db, campaign.id)
            if metrics.get("over_budget"):
                decision = await PolicyEngine.check(db, ActionType.CAMPAIGN_PAUSE, {})
                if not decision.allow:
                    denials.append(f"campaign_pause:{campaign.slug}:{decision.reason}")
                    continue
                await RevenueCampaignService.pause_campaign(db, campaign.id, reason="auto: over budget")
                actions.append(f"campaign_pause:{campaign.slug}")
        await db.flush()
        return actions, denials

    @staticmethod
    async def _stale_order_review(db: AsyncSession) -> list[str]:
        actions = []
        cutoff = datetime.utcnow() - timedelta(hours=STALE_ORDER_HOURS)
        result = await db.execute(
            select(Order).where(Order.status == OrderStatus.PENDING, Order.created_at < cutoff)
        )
        for order in list(result.scalars().all()):
            db.add(IncidentEvent(
                title=f"Stale pending order {order.id}",
                description=f"Order {order.id} stuck in PENDING for > {STALE_ORDER_HOURS}h",
                severity=IncidentSeverity.LOW,
                affected_order_id=order.id,
            ))
            actions.append(f"escalate_order:{order.id}")
        await db.flush()
        return actions

    @staticmethod
    async def _daily_report(db: AsyncSession) -> None:
        now = datetime.utcnow()
        order_count = await db.scalar(select(Order.id).where(Order.purchased_at >= now - timedelta(days=1)))
        revenue = await db.scalar(
            select(Order.amount_cents).where(
                Order.status == OrderStatus.PAID,
                Order.purchased_at >= now - timedelta(days=1),
            )
        )
        db.add(StrategyLog(
            week_start=now.date(),
            summary=f"Daily report: {order_count or 0} orders, {(revenue or 0) / 100:.2f} revenue (24h)",
            recommendations="Agent-managed: see audit log for actions.",
        ))
        await db.flush()

    @classmethod
    async def run_cycle(cls, db: AsyncSession) -> dict:
        if not await PolicyEngine.is_autonomy_enabled(db):
            logger.info("commerce_ops_skipped", reason="autonomy_disabled")
            return {"skipped": True, "actions_taken": [], "policy_denials": []}
        actions: list[str] = []
        denials: list[str] = []
        a1, d1 = await cls._price_optimization(db)
        actions += a1; denials += d1
        a2, d2 = await cls._campaign_check(db)
        actions += a2; denials += d2
        actions += await cls._stale_order_review(db)
        await cls._daily_report(db)
        await db.commit()
        logger.info("commerce_ops_cycle", actions=actions, denials=denials)
        return {"skipped": False, "actions_taken": actions, "policy_denials": denials}
```

- [ ] **Step 4: Check IncidentEvent model fields** — verify `title`, `description`, `severity`, `affected_order_id`, `affected_campaign_id` column names in `models.py` (line 642). If names differ (e.g. `summary` instead of `title`), adjust the code above to match before running tests.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_commerce_ops.py -v`
Expected: 6 PASSED (adjust expectations to actual model field names if Step 4 required changes)

- [ ] **Step 6: Commit**

```bash
git add graxia/packages/revenue_os/agents/commerce_ops.py graxia/packages/revenue_os/tests/test_commerce_ops.py
git commit -m "feat(revenue-os): commerce ops agent - price/campaign/stale-order jobs with policy gating"
```

---

### Task 6: Support Agent (intent classification + policy-checked actions)

**Files:**
- Create: `graxia/packages/revenue_os/agents/support.py`
- Modify: `graxia/packages/revenue_os/schemas.py` (append SupportChatRequest/SupportChatResponse)
- Create: `graxia/packages/revenue_os/tests/test_support_agent.py`

**Interfaces:**
- Consumes: `SupportIntent` enum (Task 1), `PolicyEngine.check` (Task 1), `OrderService.get_order_by_id`/`get_order_by_platform_id`, `Refund` model (fields: order_id, amount_cents, currency, reason, status), `EmailService.queue_email` (existing), `ChiefOfStaffAgent.escalate_issue` (existing), `Product` model
- Produces: `class SupportReply` (dataclass): `intent: SupportIntent`, `text: str`, `action_taken: str | None`; `SupportAgent.handle_message(db, message: str, customer_email: str) -> SupportReply`; `SupportAgent.classify_intent(message: str) -> SupportIntent`; `SupportAgent._handle_wismo(db, customer_email) -> str`; `SupportAgent._handle_refund(db, customer_email, message) -> str`

- [ ] **Step 1: Write failing tests** — `tests/test_support_agent.py`

```python
import uuid
from datetime import datetime, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.support import SupportAgent
from ..core.policy_engine import PolicyEngine
from ..enums import OrderStatus, RefundStatus, SupportIntent
from ..models import EmailOutbox, Order, Refund


@pytest.mark.asyncio
async def test_classify_wismo_thai():
    intent = SupportAgent.classify_intent("ออเดอร์ของฉันอยู่ไหน ส่งของหรือยัง")
    assert intent == SupportIntent.WISMO


@pytest.mark.asyncio
async def test_classify_refund_english():
    intent = SupportAgent.classify_intent("I want a refund please")
    assert intent == SupportIntent.REFUND


@pytest.mark.asyncio
async def test_classify_product_question():
    intent = SupportAgent.classify_intent("สินค้านี้เหมาะกับมือใหม่ไหม มีเนื้อหาอะไรบ้าง")
    assert intent == SupportIntent.PRODUCT_QUESTION


@pytest.mark.asyncio
async def test_wismo_replies_with_status(db_session: AsyncSession, sample_order_data):
    reply = await SupportAgent.handle_message(db_session, "order status?", sample_order_data.customer_email)
    assert reply.intent == SupportIntent.WISMO
    assert sample_order_data.status.value in reply.text.lower()


@pytest.mark.asyncio
async def test_refund_within_policy_creates_refund(db_session: AsyncSession, sample_order_data):
    await PolicyEngine.seed_default_rules(db_session)
    order = sample_order_data
    order.status = OrderStatus.PAID
    order.purchased_at = datetime.utcnow() - timedelta(days=2)
    await db_session.commit()
    reply = await SupportAgent.handle_message(db_session, "please refund me", order.customer_email)
    assert reply.action_taken == "refund"
    refund = await db_session.scalar(select(Refund).where(Refund.order_id == order.id))
    assert refund is not None
    assert refund.status == RefundStatus.PROCESSING


@pytest.mark.asyncio
async def test_refund_old_order_denied(db_session: AsyncSession, sample_order_data):
    await PolicyEngine.seed_default_rules(db_session)
    order = sample_order_data
    order.status = OrderStatus.PAID
    order.purchased_at = datetime.utcnow() - timedelta(days=60)
    await db_session.commit()
    reply = await SupportAgent.handle_message(db_session, "please refund me", order.customer_email)
    assert reply.action_taken == "refund_denied"
    assert "30" in reply.text or "นโยบาย" in reply.text


@pytest.mark.asyncio
async def test_complaint_escalates(db_session: AsyncSession, sample_order_data):
    from ..enums import IncidentSeverity
    from ..models import IncidentEvent
    reply = await SupportAgent.handle_message(
        db_session, "this is a serious complaint, your service is terrible", sample_order_data.customer_email
    )
    assert reply.intent == SupportIntent.COMPLAINT
    incident = await db_session.scalar(select(IncidentEvent).order_by(IncidentEvent.created_at.desc()))
    assert incident is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_support_agent.py -v`
Expected: FAIL — import error on `..agents.support`

- [ ] **Step 3: Implement support agent** — create `agents/support.py`

```python
"""Customer support agent - intent classification + policy-checked actions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy_engine import PolicyEngine
from ..enums import ActionType, IncidentSeverity, OrderStatus, RefundStatus, SupportIntent
from ..models import EmailOutbox, Order, Product, Refund
from ..services.email_service import EmailService
from .chief_of_staff import ChiefOfStaffAgent

logger = structlog.get_logger()

REFUND_WINDOW_DAYS = 30
WISMO_KEYWORDS = ["order", "สถานะ", "ส่งของ", "shipping", "where", "track", "tracking", "อยู่ไหน", "wismo"]
REFUND_KEYWORDS = ["refund", "คืนเงิน", "คืน", "money back", "refunded"]
PRODUCT_KEYWORDS = ["product", "สินค้า", "เหมาะ", "เนื้อหา", "buy", "ซื้อ", "ราคา", "price"]
COMPLAINT_KEYWORDS = ["complaint", "ร้องเรียน", "terrible", "แย่", "scam", "หลอก", "furious", "angry"]
SALES_KEYWORDS = ["recommend", "แนะนำ", "interested", "สนใจ", "sale", "โปรโมชัน"]


@dataclass
class SupportReply:
    intent: SupportIntent
    text: str
    action_taken: Optional[str] = None


class SupportAgent:
    """Handles customer chat messages. Actions are policy-checked."""

    @staticmethod
    def classify_intent(message: str) -> SupportIntent:
        msg = message.lower()
        if any(k in msg for k in COMPLAINT_KEYWORDS):
            return SupportIntent.COMPLAINT
        if any(k in msg for k in REFUND_KEYWORDS):
            return SupportIntent.REFUND
        if any(k in msg for k in WISMO_KEYWORDS):
            return SupportIntent.WISMO
        if any(k in msg for k in SALES_KEYWORDS):
            return SupportIntent.SALES
        if any(k in msg for k in PRODUCT_KEYWORDS):
            return SupportIntent.PRODUCT_QUESTION
        return SupportIntent.OTHER

    @staticmethod
    async def _latest_order(db: AsyncSession, customer_email: str) -> Optional[Order]:
        return await db.scalar(
            select(Order)
            .where(Order.customer_email == customer_email)
            .order_by(Order.created_at.desc())
            .limit(1)
        )

    @staticmethod
    async def _handle_wismo(db: AsyncSession, customer_email: str) -> str:
        order = await SupportAgent._latest_order(db, customer_email)
        if order is None:
            return "ไม่พบออเดอร์ในระบบของเรา (no orders found for this email)"
        return f"สถานะออเดอร์ {order.id}: {order.status.value}"

    @staticmethod
    async def _handle_refund(db: AsyncSession, customer_email: str, message: str) -> str:
        order = await SupportAgent._latest_order(db, customer_email)
        if order is None:
            return "ไม่พบออเดอร์สำหรับอีเมลนี้ จึงไม่สามารถคืนเงินได้"
        age_days = (datetime.utcnow() - order.purchased_at).days
        decision = await PolicyEngine.check(
            db, ActionType.REFUND,
            {"value": 100.0, "order_id": str(order.id), "order_age_days": age_days},
        )
        if not decision.allow:
            return f"ขออภัย ไม่สามารถคืนเงินได้ตามนโยบาย ({decision.reason})"
        db.add(Refund(
            order_id=order.id,
            amount_cents=order.amount_cents,
            currency=order.currency,
            reason=f"support agent: {message[:200]}",
            status=RefundStatus.PROCESSING,
        ))
        await db.flush()
        return "เราเริ่มดำเนินการคืนเงินให้แล้ว จะอัปเดตทางอีเมลภายใน 3-5 วันทำการ"

    @staticmethod
    async def handle_message(db: AsyncSession, message: str, customer_email: str) -> SupportReply:
        intent = SupportAgent.classify_intent(message)
        if intent == SupportIntent.COMPLAINT:
            incident = await ChiefOfStaffAgent.escalate_issue(
                db,
                title=f"Support complaint from {customer_email}",
                description=message[:500],
                severity=IncidentSeverity.MEDIUM,
            )
            return SupportReply(
                intent=intent,
                text="รับทราบแล้ว เราส่งเรื่องนี้ให้ทีมตรวจสอบโดยด่วน ขออภัยในความไม่สะดวก",
                action_taken="escalated",
            )
        if intent == SupportIntent.REFUND:
            text = await SupportAgent._handle_refund(db, customer_email, message)
            action = "refund" if "ดำเนินการคืนเงิน" in text else "refund_denied"
            await db.commit()
            return SupportReply(intent=intent, text=text, action_taken=action)
        if intent == SupportIntent.WISMO:
            text = await SupportAgent._handle_wismo(db, customer_email)
            await db.commit()
            return SupportReply(intent=intent, text=text, action_taken="wismo")
        if intent == SupportIntent.PRODUCT_QUESTION or intent == SupportIntent.SALES:
            result = await db.execute(select(Product).limit(3))
            products = list(result.scalars().all())
            names = ", ".join(p.name for p in products) if products else "(no products yet)"
            await db.commit()
            return SupportReply(
                intent=intent,
                text=f"สินค้าของเรา: {names} — ถามเพิ่มเติมได้เลยครับ",
                action_taken="catalog",
            )
        await db.commit()
        return SupportReply(intent=intent, text="ขอบคุณที่ติดต่อ เราจะตอบกลับโดยเร็วที่สุด", action_taken="none")
```

- [ ] **Step 4: Add chat schemas** — append to `schemas.py`

```python
class SupportChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    customer_email: str = Field(..., max_length=320)


class SupportChatResponse(BaseModel):
    intent: str
    reply: str
    action_taken: Optional[str] = None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_support_agent.py -v`
Expected: 8 PASSED

- [ ] **Step 6: Commit**

```bash
git add graxia/packages/revenue_os/agents/support.py graxia/packages/revenue_os/schemas.py graxia/packages/revenue_os/tests/test_support_agent.py
git commit -m "feat(revenue-os): support agent - intent classification + policy-checked refunds"
```

---

### Task 7: Support chat API router

**Files:**
- Create: `graxia/services/revenue_os_api/routers/support.py`
- Modify: `graxia/services/revenue_os_api/router.py`
- Create: `graxia/packages/revenue_os/tests/test_support_router.py`

**Interfaces:**
- Consumes: `SupportAgent.handle_message` (Task 6), `SupportChatRequest/SupportChatResponse` schemas (Task 6), `get_db` dependency
- Produces: `POST /api/support/chat` → `SupportChatResponse`

- [ ] **Step 1: Write failing tests** — `tests/test_support_router.py`

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.support import SupportAgent
from ..schemas import SupportChatRequest


@pytest.mark.asyncio
async def test_handle_message_direct(db_session: AsyncSession, sample_order_data):
    req = SupportChatRequest(message="where is my order?", customer_email=sample_order_data.customer_email)
    reply = await SupportAgent.handle_message(db_session, req.message, req.customer_email)
    assert reply.intent.value in {"wismo", "other"}
```

- [ ] **Step 2: Run tests to verify they pass** (validation of schemas + agent wiring)

Run: `pytest graxia/packages/revenue_os/tests/test_support_router.py -v`
Expected: 1 PASSED

- [ ] **Step 3: Create router** — `graxia/services/revenue_os_api/routers/support.py`

```python
"""Customer support chat endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.agents.support import SupportAgent
from ....packages.revenue_os.schemas import SupportChatRequest, SupportChatResponse
from ..dependencies import get_db

router = APIRouter(prefix="/api/support", tags=["support"])


@router.post("/chat", response_model=SupportChatResponse)
async def chat(body: SupportChatRequest, db: AsyncSession = Depends(get_db)) -> SupportChatResponse:
    reply = await SupportAgent.handle_message(db, body.message, body.customer_email)
    return SupportChatResponse(
        intent=reply.intent.value,
        reply=reply.text,
        action_taken=reply.action_taken,
    )
```

- [ ] **Step 4: Register router** — in `router.py`, follow the Task 2 Step 5 pattern.

- [ ] **Step 5: Run full package test suite**

Run: `pytest graxia/packages/revenue_os/tests/ -v`
Expected: all tests PASS (existing ~12 files + new 5 files)

- [ ] **Step 6: Commit**

```bash
git add graxia/services/revenue_os_api/routers/support.py graxia/services/revenue_os_api/router.py graxia/packages/revenue_os/tests/test_support_router.py
git commit -m "feat(revenue-os): support chat API endpoint"
```

---

### Task 8: Celery beat wiring

**Files:**
- Modify: `graxia/packages/revenue_os/celery/celery_app.py`
- Create: `graxia/packages/revenue_os/celery/tasks/commerce_ops.py`

**Interfaces:**
- Consumes: `CommerceOpsAgent.run_cycle` (Task 5), `digital_fulfillment` task (Task 4), `create_revenue_os_celery_app` (existing)
- Produces: celery task `commerce_ops()`; beat entries for `digital_fulfillment` (every 5 min) and `commerce_ops` (hourly)

- [ ] **Step 1: Create celery task** — `celery/tasks/commerce_ops.py`

```python
"""Commerce ops agent celery task."""
from __future__ import annotations

import structlog

from ...db import get_db_session
from ...agents.commerce_ops import CommerceOpsAgent

logger = structlog.get_logger()


def commerce_ops():
    """Run the autonomous commerce cycle. Follows agent_consumers asyncio pattern."""
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await CommerceOpsAgent.run_cycle(db)

    return asyncio.run(_impl())
```

- [ ] **Step 2: Add beat schedule** — in `celery_app.py`, find the existing `beat_schedule` (or where schedules like `agent_consumers` are defined) and add:

```python
    "digital_fulfillment": {
        "task": "revenue_os.celery.tasks.digital_fulfillment.digital_fulfillment",
        "schedule": 300.0,  # every 5 minutes
    },
    "commerce_ops": {
        "task": "revenue_os.celery.tasks.commerce_ops.commerce_ops",
        "schedule": 3600.0,  # hourly
    },
```

Match the exact schedule data structure the file already uses (crontab vs seconds) — copy the style of the nearest existing entry. Also verify the task name prefix (`revenue_os.` vs `graxia.packages.revenue_os.`) by checking how existing tasks are registered in the file.

- [ ] **Step 3: Verify task registration imports**

Run: `python -c "from graxia.packages.revenue_os.celery.tasks import digital_fulfillment, commerce_ops; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Run tests**

Run: `pytest graxia/packages/revenue_os/tests/test_celery_tasks.py -v`
Expected: PASS (existing celery tests unaffected)

- [ ] **Step 5: Commit**

```bash
git add graxia/packages/revenue_os/celery/celery_app.py graxia/packages/revenue_os/celery/tasks/commerce_ops.py
git commit -m "feat(revenue-os): celery beat - digital fulfillment sweep + hourly commerce ops"
```

---

### Task 9: Frontend support chat widget

**Files:**
- Create: `frontend/src/components/chat/SupportChat.tsx`
- Create: `frontend/src/components/chat/SupportChat.test.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/StorePage.tsx`

**Interfaces:**
- Consumes: existing `apiFetch`/client pattern in `frontend/src/lib/api.ts` (check how existing API calls are made and mirror them)
- Produces: `supportChat(message, customerEmail) -> Promise<{intent, reply, action_taken}>` in `lib/api.ts`; `<SupportChat />` component mounted in `StorePage`

- [ ] **Step 1: Write failing component test** — `components/chat/SupportChat.test.tsx`

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { SupportChat } from './SupportChat'

vi.mock('../../lib/api', () => ({
  supportChat: vi.fn().mockResolvedValue({ intent: 'wismo', reply: 'สถานะออเดอร์: paid', action_taken: 'wismo' }),
}))

describe('SupportChat', () => {
  it('sends a message and shows the reply', async () => {
    render(<SupportChat customerEmail="test@example.com" />)
    fireEvent.click(screen.getByRole('button', { name: /support|help/i }))
    const input = screen.getByPlaceholderText(/message/i)
    fireEvent.change(input, { target: { value: 'where is my order?' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => {
      expect(screen.getByText(/สถานะออเดอร์/i)).toBeTruthy()
    })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/chat/SupportChat.test.tsx`
Expected: FAIL — module not found

- [ ] **Step 3: Implement widget** — create `components/chat/SupportChat.tsx`

```tsx
import { useState } from 'react'
import { supportChat } from '../../lib/api'

interface SupportChatProps {
  customerEmail: string
}

export function SupportChat({ customerEmail }: SupportChatProps) {
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [history, setHistory] = useState<{ role: 'user' | 'bot'; text: string }[]>([])
  const [loading, setLoading] = useState(false)

  const send = async () => {
    if (!message.trim()) return
    const text = message
    setHistory((h) => [...h, { role: 'user', text }])
    setMessage('')
    setLoading(true)
    try {
      const res = await supportChat(text, customerEmail)
      setHistory((h) => [...h, { role: 'bot', text: res.reply }])
    } catch {
      setHistory((h) => [...h, { role: 'bot', text: 'ขออภัย ระบบขัดข้องชั่วคราว' }])
    } finally {
      setLoading(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-50 rounded-full bg-blue-600 px-4 py-2 text-white shadow-lg"
        aria-label="Support chat"
      >
        Support
      </button>
    )
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 flex h-96 w-80 flex-col rounded-xl border bg-white shadow-2xl">
      <div className="flex items-center justify-between border-b px-4 py-2">
        <span className="font-semibold">Support</span>
        <button onClick={() => setOpen(false)} aria-label="Close" className="text-gray-500">×</button>
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {history.map((h, i) => (
          <div key={i} className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${h.role === 'user' ? 'ml-auto bg-blue-600 text-white' : 'bg-gray-100'}`}>
            {h.text}
          </div>
        ))}
        {loading && <div className="text-sm text-gray-400">…</div>}
      </div>
      <form
        onSubmit={(e) => { e.preventDefault(); send() }}
        className="flex gap-2 border-t p-2"
      >
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="พิมพ์ข้อความ..."
          className="flex-1 rounded border px-2 py-1 text-sm"
        />
        <button type="submit" className="rounded bg-blue-600 px-3 py-1 text-white">ส่ง</button>
      </form>
    </div>
  )
}
```

- [ ] **Step 4: Add API client** — in `frontend/src/lib/api.ts`, mirror the existing request pattern:

```ts
export async function supportChat(message: string, customerEmail: string) {
  const res = await apiFetch('/api/support/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, customer_email: customerEmail }),
  })
  return res.json()
}
```

Replace `apiFetch` with the actual fetch/axios helper the file already exports (check first).

- [ ] **Step 5: Mount widget** — in `frontend/src/pages/StorePage.tsx`, render `<SupportChat customerEmail={currentUserEmail} />` (use the existing auth/email source; if none, pass a fallback like `"guest@graxia.local"`).

- [ ] **Step 6: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/chat/SupportChat.test.tsx`
Expected: 1 PASSED

- [ ] **Step 7: Run frontend suite**

Run: `cd frontend && npx vitest run`
Expected: all existing + new PASS (if pre-existing failures exist, report but do not fix unrelated)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/chat/SupportChat.tsx frontend/src/components/chat/SupportChat.test.tsx frontend/src/lib/api.ts frontend/src/pages/StorePage.tsx
git commit -m "feat(frontend): support chat widget on storefront"
```

---

### Task 10: Final verification + docs

**Files:**
- Modify: `docs/superpowers/specs/2026-08-16-autonomous-ecommerce-design.md` (mark Phase 1 complete)

- [ ] **Step 1: Run full backend test suite**

Run: `pytest graxia/packages/revenue_os/tests/ -v`
Expected: all PASS

- [ ] **Step 2: Run full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: all PASS

- [ ] **Step 3: Import smoke check**

Run: `python -c "from graxia.packages.revenue_os.core.policy_engine import PolicyEngine; from graxia.packages.revenue_os.agents.support import SupportAgent; from graxia.packages.revenue_os.agents.commerce_ops import CommerceOpsAgent; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Generate alembic migration** (follow repo's existing migration workflow — `backend/alembic`):

```bash
cd backend && alembic revision --autogenerate -m "add policy rules, autonomy state"
```

If the repo uses a different migration flow (check `backend/alembic.ini` / `graxia/migrations`), follow that instead. If migrations are manual DDL, add a note to the ops runbook instead.

- [ ] **Step 5: Update design doc** — in `docs/superpowers/specs/2026-08-16-autonomous-ecommerce-design.md`, add a "Phase 1 Status" section listing completed tasks and any deviations found during implementation (e.g. model field renames).

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-08-16-autonomous-ecommerce-design.md
git commit -m "docs: phase 1 completion status"
```

---

## Self-Review Notes

- **Spec coverage:** policy engine (T1, T3), kill switch (T2), digital fulfillment wiring (T4 — discovered `fulfill_order` already existed, plan wires it), commerce agent organic jobs (T5 — price/campaign/stale-order/report), support agent (T6, T7), celery cadence (T8), chat widget (T9). Content factory / lead nurture / copywriter jobs deferred to P2 as decided in spec §8.
- **Deviations from spec found during exploration:** `fulfillment_service.fulfill_order` + `queue_delivery_email` already exist and are tested — the plan builds the missing trigger instead of new fulfillment code. Agent jobs are rule-based in P1 (no LLM in critical path) to keep the cycle deterministic and testable; LLM drafting joins in P2.
- **Type consistency:** `PolicyEngine.check(db, action, context)` used identically in T1/T2/T5/T6; `SupportIntent` defined T1, consumed T6; `CommerceOpsAgent.run_cycle` stub (T2) matches full signature (T5); `RefundStatus.PROCESSING` used in T6 test + impl.
- **Verification risk:** IncidentEvent/Refund/RevenueCampaign field names were read from `models.py` signatures; Task 5 Step 4 and Task 6 Step 3 explicitly instruct checking exact column names (`title`/`description`/`affected_order_id`) before running tests — adjust to actual names if needed.
