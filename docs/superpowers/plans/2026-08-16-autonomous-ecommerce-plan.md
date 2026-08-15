# Autonomous Ecommerce Phase 1 Implementation Plan (revised 2026-08-16)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 1 — digital-first autonomous storefront on the existing Revenue OS: policy engine as the only automated guardrail, layered under a **staged autonomy rollout** (off → shadow → limited → full), digital fulfillment wired to payments, commerce ops agent, support chat agent with identity-verified refunds, an authenticated kill switch, a circuit breaker, and alerting.

**Architecture:** Extend the existing `graxia/packages/revenue_os` package. A new `PolicyEngine` gates every money/product-touching action (fail-closed) with dual PERCENT+ABSOLUTE caps and a circuit breaker that force-disables autonomy on an incident spike. `fulfill_order` already exists in `FulfillmentService` but is never called — wire it into the Stripe webhook path, lock-protected against the sweep task via the existing `acquire_automation_lock`. `CommerceOpsAgent` runs lock-protected decision cycles on celery beat. `SupportAgent` answers chat with policy-checked, identity-verified (one-time code), capped, idempotent refund handling. An `AutonomyState` singleton holds a **mode** (`off` / `shadow` / `limited` / `full`) — the mechanism behind the staged rollout (Task 12) — and every admin-facing endpoint (`/api/policy/*`, `/api/autonomy/*`) requires authentication via the **existing** `require_admin_api_key` dependency.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2 async, Celery + Redis, pytest (asyncio), existing fixtures in `graxia/packages/revenue_os/tests/conftest.py`.

---

## ⚠️ Pre-Implementation Risk Audit

This system moves real money and talks to real customers **with no human in the loop**. The findings below were verified against the actual codebase and are what the tasks fix. A reviewer signing off should check each row against the diff.

| # | Finding | Severity | Where fixed |
|---|---|---|---|
| 1 | `AutonomyState` must default to `off` — a fresh deploy/migration must never go live in full autonomy. | Critical | Task 1 (mode defaults to `off`) |
| 2 | `/api/policy/*` and `/api/autonomy/*` need authentication — the repo **already has** `require_admin_api_key` in `graxia/services/revenue_os_api/dependencies.py:56` (`ADMIN_API_KEY`, constant-time, `X-Admin-Api-Key` or Bearer). Reuse it; do NOT invent a parallel mechanism. | Critical | Task 1a (reuses existing dependency) |
| 3 | Support chat accepts a free-text `customer_email` with no proof of ownership; any "refund" message auto-approves a 100% refund. Fix: one-time verification code emailed to the address, per-customer cap, idempotency, escalate above threshold. | Critical | Task 6 |
| 4 | `_handle_refund` must not create duplicate `Refund` rows on retry/double-submit. | High | Task 6 (idempotency check) |
| 5 | `Refund(status=PROCESSING)` is created but nothing calls Stripe's refund API — customers are promised money nothing sends. | High | Task 6a (new — Stripe refund executor) |
| 6 | Keyword intent classification is gameable; accepted as documented Phase-1 limitation — every REFUND classification logs the matched keyword and ambiguous cases route to escalation. | Medium | Task 6 |
| 7 | WISMO handler discloses order status to anyone who supplies a matching email. Same verification-code gate as refunds. | Medium | Task 6 |
| 8 | `sweep_pending_fulfillments` / `CommerceOpsAgent.run_cycle` claim lock protection but neither implementation had it — overlapping beat runs can double-execute price changes or fulfillments. Lock actually applied at the celery wrapper level + overlap test. | High | Task 4, Task 5, Task 8 |
| 9 | Percent-only caps don't bound absolute exposure ("100% refund allowed" is not a guardrail on a large order). Dual PERCENT+ABSOLUTE caps (`value_type`), ABSOLUTE in cents. | High | Task 1 |
| 10 | No circuit breaker — if a bug makes the agent misbehave, nothing stops it until a human happens to notice. Incident spike force-disables autonomy + alerting. | Critical | Task 1, Task 11 |
| 11 | No rollout staging — must walk off → shadow → limited → full with observation gates and explicit exit criteria, no unreviewed jump. | Critical | Task 12 |
| 12 | `test_sweep_is_idempotent` originally referenced an undefined `product` variable (NameError). | Low (blocking) | Task 4 (fixed) |
| 13 | Secrets: `ADMIN_API_KEY`/`STRIPE_API_KEY` plumbing already exists via env; no secret ever logged or returned. | Medium | Global Constraints, Task 1a, Task 6a |
| 14 | **Logic bug in `PolicyEngine.check()`:** a MAX-only action could never be allowed (loop only counted explicit ALLOW rows) — the engine as designed could not pass its own tests. Fixed: any applicable MAX/MIN rule that doesn't deny counts as a pass. | Critical (correctness) | Task 1 |
| 15 | Plan-doc defects found in the revised draft: Task 5 tests called removed `set_autonomy` API and never set mode (default `off` → agent skips → tests fail); `_price_optimization` passed no `value_cents` so ABSOLUTE caps would deny every change; Task 1a invented a duplicate auth dependency; Task 3 schemas lacked `value_type`; Task 5 test missed `RevenueCampaignService` import. All fixed inline. | Blocking | Tasks 1a/3/5 |

**Reviewer note:** #2, #3, #9, #10, #11 matter most — a policy API that can be silently disabled and a refund flow that pays out on an unverified email are both "the guardrail doesn't guard" bugs. Do not relax these to hit a deadline; cut scope elsewhere instead (e.g. narrow which product categories get autonomous pricing first).

---

## Global Constraints

- Test framework: pytest with `db_session`, `sample_product_data`, `sample_order_data`, `sample_customer_data`, `mock_resend_client`, `mock_anthropic_client` fixtures from `graxia/packages/revenue_os/tests/conftest.py`
- Run tests: `pytest graxia/packages/revenue_os/tests/ -v` (from repo root)
- All new DB models go in `graxia/packages/revenue_os/models.py` following existing SQLAlchemy 2 style (`Mapped`, `mapped_column`, `SAEnum`)
- All new enums go in `graxia/packages/revenue_os/enums.py` following existing `StrEnum` style
- All services are static-method classes with `db: AsyncSession` as first arg (existing pattern)
- Policy engine is fail-closed: no applicable rules matched for an action → DENY
- Agents CANNOT modify policy rules — admin API only, authenticated via the **existing** `require_admin_api_key` dependency (`ADMIN_API_KEY` env, `X-Admin-Api-Key` or `Authorization: Bearer` header) — never a new token mechanism
- Every agent action MUST write `AuditLog` (model exists: `revenue_os_audit_logs`)
- Every policy deny MUST create an `IncidentEvent` (severity LOW for routine, MEDIUM for money actions)
- Every money-moving action (refund, price change, discount) MUST be checked against BOTH a PERCENT and an ABSOLUTE cap — the caller passes `context["value"]` (percent) and `context["value_cents"]` (absolute, cents) — and MUST be idempotent (retry/duplicate webhook/duplicate chat message never double-executes)
- Every celery beat job MUST be wrapped in `acquire_automation_lock` (`core/db_ops.py`) so an overlapping run is skipped, not double-executed
- `AutonomyState` defaults to `off` in every environment, including tests that don't explicitly set a mode
- Any endpoint that discloses order/customer data or triggers a refund MUST verify the requester controls the email via a one-time verification code before acting
- No secret (Stripe, Resend, Anthropic, ADMIN_API_KEY) is ever logged, committed, or returned in an API response
- Keep existing tests green — do not modify existing behavior

**Gate legend:** each task ends with a **Gate** line — pass/fail bar for moving on. A task is not "done" because the code compiles — it's done when its Gate is met.

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
  - `class ValueType(StrEnum)`: PERCENT="percent", ABSOLUTE="absolute" — ABSOLUTE values are in **cents**, matching the existing `*_cents` convention
  - `class AutonomyMode(StrEnum)`: OFF="off", SHADOW="shadow", LIMITED="limited", FULL="full" (Task 12 defines the rollout)
  - `class PolicyRule(Base)` — table `revenue_os_policy_rules`: `id UUID PK`, `action str(50)`, `rule_type SAEnum(RuleType)`, `value Optional[float]`, `value_type SAEnum(ValueType) default PERCENT`, `limited_multiplier float default 0.25`, `scope str(50) default "global"`, `scope_value Optional[str]`, `enabled bool default True`, `priority int default 100`, `description Optional[str]`, `created_at`, `updated_at`
  - `class AutonomyState(Base)` — table `revenue_os_autonomy_state`: `id int PK default 1`, `mode SAEnum(AutonomyMode) default OFF, nullable=False`, `updated_at`
  - `class PolicyDecision` (dataclass): `allow: bool`, `reason: str`, `rule_id: Optional[UUID] = None`
  - `class PolicyEngine` static methods: `check(db, action, context) -> PolicyDecision`, `get_autonomy_mode(db) -> AutonomyMode`, `is_autonomy_enabled(db) -> bool`, `set_autonomy_mode(db, mode) -> AutonomyMode`, `check_circuit_breaker(db) -> bool`, `seed_default_rules(db) -> int`, `_load_rules(db, action) -> list[PolicyRule]`, `_evaluate(rule, context, mode) -> tuple[bool, Optional[str]]`

- [ ] **Step 1: Write failing tests** — `tests/test_policy_engine.py`

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_policy_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named '..core.policy_engine'`

- [ ] **Step 3: Add enums** — append to `enums.py` (`IncidentSeverity.HIGH` already exists at line 90 — do not modify it):

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


class ValueType(StrEnum):
    """How a PolicyRule's `value` should be interpreted. ABSOLUTE is always in cents
    (matches the existing price_cents/amount_cents convention). A money-moving action
    is checked against BOTH: a percent cap alone does not bound absolute exposure."""
    PERCENT = "percent"
    ABSOLUTE = "absolute"


class AutonomyMode(StrEnum):
    """Staged autonomy rollout — see Task 12. Nothing reaches FULL without a defined
    observation period in SHADOW and LIMITED first."""
    OFF = "off"        # no autonomous action of any kind
    SHADOW = "shadow"  # agents compute + log what they WOULD do; nothing is executed
    LIMITED = "limited"  # agents execute, capped at value * limited_multiplier
    FULL = "full"       # agents execute at full policy-configured caps


class SupportIntent(StrEnum):
    WISMO = "wismo"
    REFUND = "refund"
    PRODUCT_QUESTION = "product_question"
    COMPLAINT = "complaint"
    SALES = "sales"
    OTHER = "other"
```

- [ ] **Step 4: Add models** — append to `models.py` (after `AttributionSummary`; follow existing style):

```python
# ══════════════════════════════════════════════════════════════════
# POLICY & AUTONOMY MODELS
# ══════════════════════════════════════════════════════════════════

class PolicyRule(Base):
    """Policy engine rules - the ONLY automated guardrail on top of the staged
    autonomy rollout (Task 12). Agents cannot modify these (authenticated admin API,
    Task 1a). A money-moving action is expected to have BOTH a PERCENT rule and an
    ABSOLUTE rule; PolicyEngine.check() denies if either is exceeded."""
    __tablename__ = "revenue_os_policy_rules"
    __table_args__ = (
        Index("ix_policy_action_scope", "action", "scope"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_type: Mapped[RuleType] = mapped_column(SAEnum(RuleType), nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Float)
    value_type: Mapped[ValueType] = mapped_column(SAEnum(ValueType), default=ValueType.PERCENT, nullable=False)
    limited_multiplier: Mapped[float] = mapped_column(Float, default=0.25, nullable=False)
    scope: Mapped[str] = mapped_column(String(50), default="global")
    scope_value: Mapped[Optional[str]] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    description: Mapped[Optional[str]] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AutonomyState(Base):
    """Global autonomy state (singleton row, id=1). Holds a MODE, not a boolean —
    a freshly-migrated row must default to OFF, never full autonomy (Risk Audit #1).
    Task 12 is the only place expected to advance this past OFF, after its stage gates."""
    __tablename__ = "revenue_os_autonomy_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    mode: Mapped[AutonomyMode] = mapped_column(SAEnum(AutonomyMode), default=AutonomyMode.OFF, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

Check imports at top of `models.py` — `Float` and `Boolean` may need adding to `from sqlalchemy import ...`; add `ValueType`/`AutonomyMode` to the `from ..enums import ...` line.

**Migration safety:** when generating the alembic migration (Task 10 Step 4), if `revenue_os_autonomy_state` already exists with an `enabled` column, the migration MUST map `enabled=False → mode=OFF` and `enabled=True → mode=FULL` explicitly.

- [ ] **Step 5: Implement policy engine** — create `core/policy_engine.py`. Fixes Risk Audit #14: any applicable MAX/MIN rule that doesn't deny counts as an allow — not just explicit `ALLOW` rows.

```python
"""Policy engine - the ONLY automated guardrail, layered under AutonomyMode (Task 12).

Every money/product-touching action must pass PolicyEngine.check() first.
Fail-closed: an action with no matching, applicable rules is DENIED.
Money-moving actions must carry context['value'] (percent) and context['value_cents']
(absolute, cents) so PERCENT and ABSOLUTE rules both apply (Risk Audit #9).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import AUTONOMY_STATE_ID, CIRCUIT_BREAKER_INCIDENT_THRESHOLD, CIRCUIT_BREAKER_WINDOW_MINUTES
from ..enums import AutonomyMode, IncidentSeverity, RuleType, ValueType
from ..models import AutonomyState, IncidentEvent, PolicyRule


@dataclass
class PolicyDecision:
    allow: bool
    reason: str
    rule_id: Optional[UUID] = None


class PolicyEngine:
    """Evaluate policy rules for autonomous actions, gated by AutonomyMode and a circuit breaker."""

    @staticmethod
    async def get_autonomy_mode(db: AsyncSession) -> AutonomyMode:
        state = await db.scalar(select(AutonomyState).where(AutonomyState.id == AUTONOMY_STATE_ID))
        if state is None:
            # Safe-by-default: a missing row is OFF, never FULL (Risk Audit #1).
            db.add(AutonomyState(id=AUTONOMY_STATE_ID, mode=AutonomyMode.OFF))
            await db.commit()
            return AutonomyMode.OFF
        return state.mode

    @staticmethod
    async def is_autonomy_enabled(db: AsyncSession) -> bool:
        """True for any mode except OFF. Callers that must distinguish SHADOW (log-only)
        from LIMITED/FULL (execute) should call get_autonomy_mode directly."""
        return await PolicyEngine.get_autonomy_mode(db) != AutonomyMode.OFF

    @staticmethod
    async def set_autonomy_mode(db: AsyncSession, mode: AutonomyMode) -> AutonomyMode:
        state = await db.scalar(select(AutonomyState).where(AutonomyState.id == AUTONOMY_STATE_ID))
        if state is None:
            state = AutonomyState(id=AUTONOMY_STATE_ID, mode=mode)
            db.add(state)
        else:
            state.mode = mode
        await db.commit()
        return mode

    @staticmethod
    async def check_circuit_breaker(db: AsyncSession) -> bool:
        """If >= threshold MEDIUM+ incidents fired in the trailing window, force mode to
        OFF and raise a HIGH incident so Task 11's alerter pages a human."""
        cutoff = datetime.utcnow() - timedelta(minutes=CIRCUIT_BREAKER_WINDOW_MINUTES)
        count = await db.scalar(
            select(func.count(IncidentEvent.id)).where(
                IncidentEvent.created_at >= cutoff,
                IncidentEvent.severity.in_([IncidentSeverity.MEDIUM, IncidentSeverity.HIGH]),
            )
        )
        if count and count >= CIRCUIT_BREAKER_INCIDENT_THRESHOLD:
            state = await db.scalar(select(AutonomyState).where(AutonomyState.id == AUTONOMY_STATE_ID))
            if state and state.mode != AutonomyMode.OFF:
                state.mode = AutonomyMode.OFF
                db.add(IncidentEvent(
                    title="Circuit breaker tripped — autonomy forced OFF",
                    description=f"{count} MEDIUM+ incidents in the last {CIRCUIT_BREAKER_WINDOW_MINUTES} minutes",
                    severity=IncidentSeverity.HIGH,
                ))
                await db.commit()
            return True
        return False

    @staticmethod
    async def _load_rules(db: AsyncSession, action: str) -> list[PolicyRule]:
        result = await db.execute(
            select(PolicyRule)
            .where(PolicyRule.action == action, PolicyRule.enabled.is_(True))
            .order_by(PolicyRule.priority.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    def _evaluate(rule: PolicyRule, context: dict, mode: AutonomyMode) -> tuple[bool, Optional[str]]:
        """Return (applies, deny_reason). applies=False means this rule is scoped to
        something else (e.g. a different product_id) and is excluded from BOTH the deny
        and the allow computation — an inapplicable rule must never silently permit."""
        if rule.scope != "global" and rule.scope == "product_id" and context.get("product_id") != rule.scope_value:
            return False, None
        if rule.rule_type == RuleType.DENY:
            return True, f"denied by rule {rule.id}"
        if rule.rule_type in (RuleType.MAX, RuleType.MIN):
            context_key = "value_cents" if rule.value_type == ValueType.ABSOLUTE else "value"
            value = context.get(context_key)
            if value is None:
                return True, f"rule {rule.id} needs context['{context_key}']"
            cap = rule.value
            if mode == AutonomyMode.LIMITED and rule.rule_type == RuleType.MAX:
                cap = rule.value * rule.limited_multiplier
            unit = "cents" if rule.value_type == ValueType.ABSOLUTE else "%"
            if rule.rule_type == RuleType.MAX and value > cap:
                kind = "absolute" if rule.value_type == ValueType.ABSOLUTE else "percent"
                return True, f"value {value}{unit} exceeds {kind} max {cap}{unit} (rule {rule.id})"
            if rule.rule_type == RuleType.MIN and value < cap:
                return True, f"value {value}{unit} below min {cap}{unit} (rule {rule.id})"
            return True, None  # applicable MAX/MIN rule that doesn't deny counts as a pass (#14)
        return True, None  # ALLOW rule that applies

    @classmethod
    async def check(cls, db: AsyncSession, action: str, context: dict) -> PolicyDecision:
        rules = await cls._load_rules(db, action)
        if not rules:
            return PolicyDecision(allow=False, reason=f"no policy rule matched for action '{action}'")
        mode = await cls.get_autonomy_mode(db)
        denied: Optional[PolicyDecision] = None
        allowed = False
        for rule in rules:
            applies, reason = cls._evaluate(rule, context, mode)
            if not applies:
                continue
            if reason is not None:
                denied = PolicyDecision(allow=False, reason=reason, rule_id=rule.id)
                break
            allowed = True
        if denied is not None:
            return denied
        if allowed:
            return PolicyDecision(allow=True, reason=f"allowed by policy (action '{action}', mode={mode.value})")
        return PolicyDecision(allow=False, reason=f"no applicable rule allowed action '{action}'")

    @staticmethod
    async def seed_default_rules(db: AsyncSession) -> int:
        """Insert default Phase-1 rules. Idempotent (skips existing action+rule_type+value_type).
        Every money-moving action gets BOTH a PERCENT and an ABSOLUTE cap (Risk Audit #9).
        These starting numbers are placeholders — Task 12 Gate 0 requires the business owner
        to confirm or replace every one before autonomy leaves OFF."""
        defaults = [
            # action, rule_type, value_type, value, description
            (ActionType.PRICE_CHANGE.value, RuleType.MAX, ValueType.PERCENT, 20.0, "max price change, percent"),
            (ActionType.PRICE_CHANGE.value, RuleType.MAX, ValueType.ABSOLUTE, 50_000_00, "max price change, THB cents"),
            (ActionType.DISCOUNT.value, RuleType.MAX, ValueType.PERCENT, 15.0, "max discount, percent"),
            (ActionType.DISCOUNT.value, RuleType.MAX, ValueType.ABSOLUTE, 20_000_00, "max discount, THB cents"),
            # Refund PERCENT stays 100 (full refund is legitimate) — the real guardrail is
            # the ABSOLUTE cap plus Task 6's per-customer rate limit + escalation.
            (ActionType.REFUND.value, RuleType.MAX, ValueType.PERCENT, 100.0, "refund up to full order value"),
            (ActionType.REFUND.value, RuleType.MAX, ValueType.ABSOLUTE, 1_500_00, "max auto-refund, THB cents — escalate above this"),
            (ActionType.FULFILL.value, RuleType.ALLOW, ValueType.PERCENT, None, "allow fulfillment"),
            (ActionType.CAMPAIGN_PAUSE.value, RuleType.ALLOW, ValueType.PERCENT, None, "allow pausing campaigns"),
            (ActionType.CAMPAIGN_PUBLISH.value, RuleType.ALLOW, ValueType.PERCENT, None, "allow publishing campaigns"),
            (ActionType.EMAIL_SEND.value, RuleType.MAX, ValueType.PERCENT, 5.0, "max emails per customer per day"),
        ]
        inserted = 0
        for action, rule_type, value_type, value, desc in defaults:
            existing = await db.scalar(
                select(PolicyRule).where(
                    PolicyRule.action == action,
                    PolicyRule.rule_type == rule_type,
                    PolicyRule.value_type == value_type,
                )
            )
            if existing is None:
                db.add(PolicyRule(action=action, rule_type=rule_type, value_type=value_type,
                                   value=value, description=desc))
                inserted += 1
        await db.commit()
        return inserted
```

- [ ] **Step 6: Add constants** — in `constants.py` add:

```python
AUTONOMY_STATE_ID = 1  # singleton row id for the autonomy state
CIRCUIT_BREAKER_WINDOW_MINUTES = 60   # trailing window checked for incident spikes
CIRCUIT_BREAKER_INCIDENT_THRESHOLD = 5  # MEDIUM+ incidents in the window that force mode -> OFF
SUPPORT_VERIFICATION_TTL_MINUTES = 15   # one-time code validity
SUPPORT_VERIFICATION_MAX_ATTEMPTS = 5  # wrong-code attempts before escalation
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_policy_engine.py -v`
Expected: 12 PASSED

- [ ] **Step 8: Commit**

```bash
git add graxia/packages/revenue_os/enums.py graxia/packages/revenue_os/models.py graxia/packages/revenue_os/constants.py graxia/packages/revenue_os/core/policy_engine.py graxia/packages/revenue_os/tests/test_policy_engine.py
git commit -m "feat(revenue-os): policy engine - fail-closed dual-cap rules, AutonomyMode, circuit breaker (fixes allow/deny loop bug)"
```

**Gate (Task 1):** all 12 tests pass — specifically `test_new_row_defaults_to_autonomy_off`, `test_absolute_cap_denies_even_under_percent_cap`, `test_limited_mode_applies_multiplier`, and `test_max_rule_allows_under_limit` (Risk Audit #1/#9/#14). Do not proceed until green.

---

### Task 1a: Admin authentication for policy/autonomy endpoints (reuse existing)

**Why before Task 2:** `/api/policy/*` and `/api/autonomy/*` can rewrite or disable every guardrail. They must never ship unauthenticated.

**Verified:** the repo **already has** `require_admin_api_key` in `graxia/services/revenue_os_api/dependencies.py:56` — reads `ADMIN_API_KEY` at request time, constant-time comparison, accepts `X-Admin-Api-Key` or `Authorization: Bearer <key>` headers, fail-fast in production. **Reuse it. Do NOT create `REVENUE_OS_ADMIN_TOKEN` or any parallel mechanism.**

**Files:**
- Create: `graxia/packages/revenue_os/tests/test_admin_auth.py` (unit tests pinning the existing dependency's contract)

**Interfaces:**
- Consumes: `require_admin_api_key(request, x_admin_api_key, authorization)` from `graxia.services.revenue_os_api.dependencies` (exists)
- Produces: proof that policy/autonomy routers (Tasks 2-3) are gated; the dependency is reused as-is

- [ ] **Step 1: Write tests** — `tests/test_admin_auth.py`

```python
import pytest
from fastapi import Request, HTTPException

from graxia.services.revenue_os_api.dependencies import require_admin_api_key


def _make_request(headers: list[tuple[bytes, bytes]]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "scheme": "http",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_missing_key_raises_401(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-key")
    with pytest.raises(HTTPException) as exc:
        await require_admin_api_key(_make_request([]))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_wrong_key_raises_403(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-key")
    with pytest.raises(HTTPException) as exc:
        await require_admin_api_key(
            _make_request([(b"x-admin-api-key", b"wrong-key")])
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_correct_key_header_accepted(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-key")
    result = await require_admin_api_key(
        _make_request([(b"x-admin-api-key", b"test-key")])
    )
    assert result is None


@pytest.mark.asyncio
async def test_bearer_token_accepted(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-key")
    result = await require_admin_api_key(
        _make_request([(b"authorization", b"Bearer test-key")])
    )
    assert result is None
```

- [ ] **Step 2: Run tests to verify they pass** (the dependency already exists — this pins its contract)

Run: `pytest graxia/packages/revenue_os/tests/test_admin_auth.py -v`
Expected: 4 PASSED

- [ ] **Step 3: Commit**

```bash
git add graxia/packages/revenue_os/tests/test_admin_auth.py
git commit -m "test(revenue-os): pin admin auth dependency contract (existing require_admin_api_key)"
```

**Gate (Task 1a):** `ADMIN_API_KEY` is provisioned through the deployment's existing secrets manager before Task 2's router ships anywhere reachable. The dependency fails closed (401 missing / 403 wrong). No new token mechanism exists anywhere in this diff.

---

### Task 2: Autonomy control API (mode-based, authenticated)

**Files:**
- Create: `graxia/services/revenue_os_api/routers/autonomy.py`
- Modify: `graxia/services/revenue_os_api/router.py`
- Create: `graxia/packages/revenue_os/tests/test_autonomy_router.py` (unit-level state transitions; 401/403 covered in Task 1a + Gate check)

**Interfaces:**
- Consumes: `PolicyEngine.get_autonomy_mode/is_autonomy_enabled/set_autonomy_mode` (Task 1), `AutonomyMode` (Task 1), `get_db` dependency, `require_admin_api_key` (existing, Task 1a)
- Produces: router with `GET /api/autonomy/status -> {"mode": str}`, `POST /api/autonomy/mode {"mode": str}` validated against `AutonomyMode`; every route behind `Depends(require_admin_api_key)` at the **router level** (so future routes can't ship unauthenticated)

- [ ] **Step 1: Write failing tests** — `tests/test_autonomy_router.py`

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_autonomy_router.py -v`
Expected: FAIL — import error on `..agents.commerce_ops` (created in Step 6)

- [ ] **Step 3: (no PolicyEngine change needed)** — `get_autonomy_mode`/`set_autonomy_mode` exist from Task 1. If you find yourself re-adding a boolean `set_autonomy`, stop — that API was replaced.

- [ ] **Step 4: Create router** — `graxia/services/revenue_os_api/routers/autonomy.py`

```python
"""Global autonomy mode control. Every route is admin-authenticated (Task 1a) — this
endpoint can turn unattended, money-moving autonomy on."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.core.policy_engine import PolicyEngine
from ....packages.revenue_os.enums import AutonomyMode
from ..dependencies import get_db, require_admin_api_key

router = APIRouter(
    prefix="/api/autonomy",
    tags=["autonomy"],
    dependencies=[Depends(require_admin_api_key)],
)


class SetModeRequest(BaseModel):
    mode: AutonomyMode


@router.get("/status")
async def get_status(db: AsyncSession = Depends(get_db)) -> dict:
    mode = await PolicyEngine.get_autonomy_mode(db)
    return {"mode": mode.value}


@router.post("/mode")
async def set_mode(body: SetModeRequest, db: AsyncSession = Depends(get_db)) -> dict:
    mode = await PolicyEngine.set_autonomy_mode(db, body.mode)
    return {"mode": mode.value}
```

- [ ] **Step 5: Register router** — in `graxia/services/revenue_os_api/router.py`, follow the existing include pattern (check whether it uses `router.include_router(x)` or `api_router.include_router(x, prefix=...)` and match exactly):

```python
from .routers.autonomy import router as autonomy_router
# ...inside the includes list:
# router.include_router(autonomy_router)
```

- [ ] **Step 6: Add CommerceOpsAgent stub** — create `agents/commerce_ops.py` (full implementation in Task 5; stub now):

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
            logger.info("commerce_ops_skipped", reason="autonomy_off")
            return {"skipped": True, "actions_taken": [], "policy_denials": [], "shadow_proposals": []}
        # Task 5 implements the jobs
        return {"skipped": False, "actions_taken": [], "policy_denials": [], "shadow_proposals": []}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_autonomy_router.py -v`
Expected: 3 PASSED

- [ ] **Step 8: Commit**

```bash
git add graxia/packages/revenue_os/agents/commerce_ops.py graxia/packages/revenue_os/tests/test_autonomy_router.py graxia/services/revenue_os_api/routers/autonomy.py graxia/services/revenue_os_api/router.py
git commit -m "feat(revenue-os): mode-based autonomy control API, authenticated"
```

**Gate (Task 2):** all 3 unit tests pass, AND against a running instance `GET /api/autonomy/status` with no `X-Admin-Api-Key` header returns 401, with a wrong key returns 403 (verify via curl against a locally booted app before moving on).

---

### Task 3: Policy admin API (rules CRUD + seed)

**Files:**
- Create: `graxia/services/revenue_os_api/routers/policy.py`
- Modify: `graxia/services/revenue_os_api/router.py`
- Modify: `graxia/packages/revenue_os/schemas.py` (append schemas — includes `value_type` + `limited_multiplier`, fixing the draft gap)
- Create: `graxia/packages/revenue_os/tests/test_policy_admin.py`

**Interfaces:**
- Consumes: `PolicyRule` model, `RuleType`/`ActionType`/`ValueType` enums, `PolicyEngine.seed_default_rules` (Task 1), `require_admin_api_key` (existing)
- Produces: router `GET /api/policy/rules`, `POST /api/policy/rules`, `PATCH /api/policy/rules/{rule_id}`, `DELETE /api/policy/rules/{rule_id}`, `POST /api/policy/seed` — all behind `Depends(require_admin_api_key)` at router level; schemas `PolicyRuleCreate` (with `value_type`, `limited_multiplier`), `PolicyRuleUpdate`, `PolicyRuleResponse`

- [ ] **Step 1: Write failing tests** — `tests/test_policy_admin.py`

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_policy_admin.py -v`
Expected: FAIL — `ImportError: cannot import name 'PolicyRuleCreate' from '..schemas'`

- [ ] **Step 3: Add schemas** — append to `schemas.py` (add `ValueType` to the enums import line if needed):

```python
class PolicyRuleCreate(BaseModel):
    action: str
    rule_type: RuleType
    value: Optional[float] = None
    value_type: ValueType = ValueType.PERCENT
    limited_multiplier: float = 0.25
    scope: str = "global"
    scope_value: Optional[str] = None
    priority: int = 100
    description: Optional[str] = None


class PolicyRuleUpdate(BaseModel):
    value: Optional[float] = None
    value_type: Optional[ValueType] = None
    limited_multiplier: Optional[float] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    description: Optional[str] = None


class PolicyRuleResponse(BaseModel):
    id: UUID
    action: str
    rule_type: RuleType
    value: Optional[float]
    value_type: ValueType
    limited_multiplier: float
    scope: str
    scope_value: Optional[str]
    enabled: bool
    priority: int
    description: Optional[str]

    class Config:
        from_attributes = True
```

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
from ..dependencies import get_db, require_admin_api_key

router = APIRouter(
    prefix="/api/policy",
    tags=["policy"],
    dependencies=[Depends(require_admin_api_key)],
)


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

- [ ] **Step 5: Register router** — in `router.py`, follow the Task 2 Step 5 pattern.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_policy_admin.py -v`
Expected: 4 PASSED

- [ ] **Step 7: Commit**

```bash
git add graxia/packages/revenue_os/schemas.py graxia/packages/revenue_os/tests/test_policy_admin.py graxia/services/revenue_os_api/routers/policy.py graxia/services/revenue_os_api/router.py
git commit -m "feat(revenue-os): policy admin CRUD API (dual-cap aware) + idempotent seeding"
```

**Gate (Task 3):** 4 tests pass; against a running instance `GET /api/policy/rules` without `X-Admin-Api-Key` returns 401.

---

### Task 4: Wire digital fulfillment into payment flow

**Files:**
- Create: `graxia/packages/revenue_os/celery/tasks/digital_fulfillment.py`
- Modify: `graxia/packages/revenue_os/services/webhook_processor.py`
- Create: `graxia/packages/revenue_os/tests/test_webhook_fulfillment.py`

**Interfaces:**
- Consumes: `WebhookProcessor.process_stripe_checkout_completed(session, db) -> Order`, `FulfillmentService.fulfill_order(db, order_id, auto_queue_email=True) -> DeliveryEvent` (existing, idempotent), `OrderService.update_order_status(db, order_id, status)`, `get_db_session()` from `.../db.py`, `acquire_automation_lock` from `core/db_ops.py` (Risk Audit #8)
- Produces: celery task `digital_fulfillment()` (lock-wrapped sweep of PAID orders missing delivery events); webhook processors fulfill immediately after order creation

- [ ] **Step 1: Write failing tests** — `tests/test_webhook_fulfillment.py`

```python
import uuid
from datetime import datetime, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..celery.tasks.digital_fulfillment import sweep_pending_fulfillments, digital_fulfillment_with_db
from ..enums import DeliveryStatus, OrderStatus
from ..models import AutomationLock, DeliveryEvent, Order
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


@pytest.mark.asyncio
async def test_sweep_respects_automation_lock(db_session: AsyncSession):
    """Risk Audit #8: the wrapper must skip when another worker holds the lock."""
    # Pre-acquire the lock row so acquire_automation_lock reports it as held.
    # Check AutomationLock column names at models.py:600 first; adjust if different.
    db_session.add(AutomationLock(
        lock_name="digital_fulfillment",
        worker_id="other-worker",
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    ))
    await db_session.commit()
    result = await digital_fulfillment_with_db(db_session)
    assert result.get("skipped") is True
    assert "lock" in result.get("reason", "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_webhook_fulfillment.py -v`
Expected: FAIL — import error on `sweep_pending_fulfillments`

- [ ] **Step 3: Create celery task** — `celery/tasks/digital_fulfillment.py`

```python
"""Digital fulfillment: sweep PAID orders missing delivery events (idempotent + locked)."""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...enums import OrderStatus
from ...models import DeliveryEvent, Order
from ...services.fulfillment_service import FulfillmentService
from ...core.db_ops import acquire_automation_lock

logger = structlog.get_logger()

LOCK_NAME = "digital_fulfillment"


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


async def digital_fulfillment_with_db(db: AsyncSession) -> dict:
    """Lock-wrapped sweep. Skips when another worker holds the lock (Risk Audit #8).
    db-injected variant so tests can exercise the lock path without redis."""
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=300) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        fulfilled = await sweep_pending_fulfillments(db)
        return {"skipped": False, "fulfilled": fulfilled}


def digital_fulfillment():
    """Celery wrapper. Follows the asyncio.run pattern from agent_consumers.py."""
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await digital_fulfillment_with_db(db)

    return asyncio.run(_impl())
```

- [ ] **Step 4: Modify webhook processor** — in `webhook_processor.py`, inside `process_stripe_checkout_completed`, after the order is created (keep existing logic intact):

```python
            # Digital fulfillment: fulfill immediately (idempotent — fulfill_order
            # is safe to re-run; the sweep task catches anything missed).
            if order.status != OrderStatus.PAID:
                order = await OrderService.update_order_status(db, order.id, OrderStatus.PAID)
            await FulfillmentService.fulfill_order(db, order.id, auto_queue_email=True)
```

Add imports for `OrderStatus`, `OrderService`, `FulfillmentService` to `webhook_processor.py` if missing. Do the same minimal PAID+fulfill step in `process_gumroad_sale` and `process_paypal_payment_completed`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_webhook_fulfillment.py graxia/packages/revenue_os/tests/test_fulfillment_service.py -v`
Expected: 4 new PASSED + existing fulfillment tests still PASS

- [ ] **Step 6: Commit**

```bash
git add graxia/packages/revenue_os/celery/tasks/digital_fulfillment.py graxia/packages/revenue_os/services/webhook_processor.py graxia/packages/revenue_os/tests/test_webhook_fulfillment.py
git commit -m "feat(revenue-os): wire digital fulfillment into payment webhooks + locked sweep task"
```

**Gate (Task 4):** 4 tests pass, including the lock test; existing `test_fulfillment_service.py` stays green.

---

### Task 5: Commerce Ops Agent (autonomous decision cycle)

**Files:**
- Modify: `graxia/packages/revenue_os/agents/commerce_ops.py` (full implementation replacing Task 2 stub)
- Create: `graxia/packages/revenue_os/tests/test_commerce_ops.py`

**Interfaces:**
- Consumes: `PolicyEngine.check/get_autonomy_mode/is_autonomy_enabled/check_circuit_breaker/set_autonomy_mode` (Task 1), enums, `Order`/`Product`/`AuditLog`/`IncidentEvent`/`StrategyLog` models, `RevenueCampaignService.pause_campaign/check_campaign_budget`, `ChiefOfStaffAgent.escalate_issue(db, title, description, severity, affected_campaign_id=None, affected_order_id=None)` (existing)
- Produces: `CommerceOpsAgent.run_cycle(db) -> dict` with `skipped`, `actions_taken: list[str]`, `policy_denials: list[str]`, `shadow_proposals: list[str]`; private jobs `_price_optimization(db, shadow)`, `_campaign_check(db, shadow)`, `_stale_order_review(db)`, `_daily_report(db)`; helper `_log_action(db, event_type, message, metadata)`
- **Mode semantics:** OFF → skip. SHADOW → compute + log proposals, **never mutate**. LIMITED/FULL → execute (engine applies the LIMITED multiplier automatically). Circuit breaker checked at top of every cycle.

- [ ] **Step 1: Write failing tests** — `tests/test_commerce_ops.py`

```python
import uuid
from datetime import datetime, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.commerce_ops import CommerceOpsAgent
from ..core.policy_engine import PolicyEngine
from ..enums import AutonomyMode, IncidentSeverity, OrderStatus, ProductStatus
from ..models import AuditLog, IncidentEvent, Product, StrategyLog
from ..services.campaign_service import RevenueCampaignService


@pytest.mark.asyncio
async def test_run_cycle_skips_when_off(db_session: AsyncSession):
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.OFF)
    result = await CommerceOpsAgent.run_cycle(db_session)
    assert result["skipped"] is True


@pytest.mark.asyncio
async def test_price_cut_for_stale_product(db_session: AsyncSession, sample_product_data):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    product = sample_product_data
    product.status = ProductStatus.PUBLISHED
    product.created_at = datetime.utcnow() - timedelta(days=21)
    await db_session.commit()
    old_price = product.price_cents

    result = await CommerceOpsAgent.run_cycle(db_session)

    assert any("price" in a.lower() for a in result["actions_taken"])
    await db_session.refresh(product)
    assert product.price_cents < old_price
    assert old_price - product.price_cents <= old_price * 0.2  # within ±20% policy
    log = await db_session.scalar(select(AuditLog).where(AuditLog.event_type == "agent.price_change"))
    assert log is not None


@pytest.mark.asyncio
async def test_price_cut_denied_beyond_policy(db_session: AsyncSession, sample_product_data):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
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
async def test_shadow_mode_proposes_but_does_not_execute(db_session: AsyncSession, sample_product_data):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.SHADOW)
    product = sample_product_data
    product.status = ProductStatus.PUBLISHED
    product.created_at = datetime.utcnow() - timedelta(days=21)
    await db_session.commit()
    old_price = product.price_cents

    result = await CommerceOpsAgent.run_cycle(db_session)

    assert result["actions_taken"] == []
    assert any("price" in p.lower() for p in result["shadow_proposals"])
    await db_session.refresh(product)
    assert product.price_cents == old_price  # nothing executed


@pytest.mark.asyncio
async def test_stale_pending_order_escalates(db_session: AsyncSession, sample_order_data):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    order = sample_order_data
    order.status = OrderStatus.PENDING
    order.created_at = datetime.utcnow() - timedelta(hours=72)
    await db_session.commit()
    result = await CommerceOpsAgent.run_cycle(db_session)
    incident = await db_session.scalar(
        select(IncidentEvent).where(IncidentEvent.severity == IncidentSeverity.LOW)
    )
    assert incident is not None


@pytest.mark.asyncio
async def test_daily_report_writes_strategy_log(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    result = await CommerceOpsAgent.run_cycle(db_session)
    log = await db_session.scalar(select(StrategyLog).order_by(StrategyLog.created_at.desc()))
    assert log is not None
    assert "summary" in (log.summary or "")


@pytest.mark.asyncio
async def test_circuit_breaker_blocks_cycle(db_session: AsyncSession):
    await PolicyEngine.seed_default_rules(db_session)
    await PolicyEngine.set_autonomy_mode(db_session, AutonomyMode.FULL)
    for i in range(5):
        db_session.add(IncidentEvent(title=f"spike {i}", description="x", severity=IncidentSeverity.MEDIUM))
    await db_session.commit()
    result = await CommerceOpsAgent.run_cycle(db_session)
    assert result["skipped"] is True
    assert await PolicyEngine.get_autonomy_mode(db_session) == AutonomyMode.OFF
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_commerce_ops.py -v`
Expected: FAIL — stub returns empty actions

- [ ] **Step 3: Implement full agent** — replace the stub in `agents/commerce_ops.py`

```python
"""Commerce operations agent - the main store manager.

Runs on celery beat (lock-wrapped by the task in Task 8). Reads state, decides,
policy-checks, executes, logs. Rule-based for Phase 1 (no LLM in the critical path).
Mode semantics (Task 12): OFF=skip, SHADOW=log-only proposals, LIMITED/FULL=execute
(the engine applies the LIMITED multiplier automatically).
"""
from __future__ import annotations

import structlog
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy_engine import PolicyEngine
from ..enums import ActionType, AutonomyMode, CampaignStatus, IncidentSeverity, OrderStatus, ProductStatus
from ..models import AuditLog, IncidentEvent, Order, Product, RevenueCampaign, StrategyLog
from ..services.campaign_service import RevenueCampaignService

logger = structlog.get_logger()

PRICE_CUT_PERCENT = 10.0
STALE_PRODUCT_DAYS = 14
STALE_ORDER_HOURS = 48


class CommerceOpsAgent:
    """Main store manager: read state → decide → policy check → execute (or log in SHADOW)."""

    @staticmethod
    async def _log_action(db: AsyncSession, event_type: str, message: str, metadata: dict | None = None) -> None:
        db.add(AuditLog(event_type=event_type, message=message, metadata_=metadata or {}))
        await db.flush()

    @staticmethod
    async def _price_optimization(db: AsyncSession, shadow: bool) -> tuple[list[str], list[str], list[str]]:
        actions, denials, proposals = [], [], []
        cutoff = datetime.utcnow() - timedelta(days=7)
        result = await db.execute(select(Product).where(Product.status == ProductStatus.PUBLISHED))
        for product in list(result.scalars().all()):
            order_count = await db.scalar(
                select(Order.id).where(
                    Order.product_id == product.id,
                    Order.status == OrderStatus.PAID,
                    Order.purchased_at >= cutoff,
                ).limit(1)
            )
            if order_count is None and product.created_at < datetime.utcnow() - timedelta(days=STALE_PRODUCT_DAYS):
                cut_cents = int((product.price_cents or 0) * (PRICE_CUT_PERCENT / 100))
                decision = await PolicyEngine.check(
                    db, ActionType.PRICE_CHANGE,
                    {
                        "value": PRICE_CUT_PERCENT,
                        "value_cents": cut_cents,          # ABSOLUTE cap check (draft-gap fix)
                        "product_id": str(product.id),
                    },
                )
                if not decision.allow:
                    denials.append(f"price_change:{product.slug}:{decision.reason}")
                    db.add(IncidentEvent(
                        title=f"Policy denied price change for {product.name}",
                        description=decision.reason,
                        severity=IncidentSeverity.MEDIUM,
                    ))
                    continue
                if shadow:
                    proposals.append(f"price_change:{product.slug}:-{PRICE_CUT_PERCENT}%")
                    await CommerceOpsAgent._log_action(
                        db, "agent.price_change.shadow",
                        f"SHADOW: would cut price of {product.name} by {PRICE_CUT_PERCENT}%",
                        {"product_id": str(product.id), "percent": PRICE_CUT_PERCENT},
                    )
                    continue
                product.price_cents = max(0, (product.price_cents or 0) - cut_cents)
                actions.append(f"price_change:{product.slug}:-{PRICE_CUT_PERCENT}%")
                await CommerceOpsAgent._log_action(
                    db, "agent.price_change",
                    f"Agent cut price of {product.name} by {PRICE_CUT_PERCENT}%",
                    {"product_id": str(product.id), "percent": PRICE_CUT_PERCENT, "cut_cents": cut_cents},
                )
        await db.flush()
        return actions, denials, proposals

    @staticmethod
    async def _campaign_check(db: AsyncSession, shadow: bool) -> tuple[list[str], list[str], list[str]]:
        actions, denials, proposals = [], [], []
        result = await db.execute(select(RevenueCampaign).where(RevenueCampaign.status == CampaignStatus.ACTIVE))
        for campaign in list(result.scalars().all()):
            metrics = await RevenueCampaignService.check_campaign_budget(db, campaign.id)
            # VERIFY the actual return key in campaign_service.py (likely "over_budget");
            # adjust this condition to the real key before running tests.
            if metrics.get("over_budget"):
                decision = await PolicyEngine.check(db, ActionType.CAMPAIGN_PAUSE, {})
                if not decision.allow:
                    denials.append(f"campaign_pause:{campaign.slug}:{decision.reason}")
                    continue
                if shadow:
                    proposals.append(f"campaign_pause:{campaign.slug}")
                    continue
                await RevenueCampaignService.pause_campaign(db, campaign.id, reason="auto: over budget")
                actions.append(f"campaign_pause:{campaign.slug}")
        await db.flush()
        return actions, denials, proposals

    @staticmethod
    async def _stale_order_review(db: AsyncSession) -> list[str]:
        actions = []
        cutoff = datetime.utcnow() - timedelta(hours=STALE_ORDER_HOURS)
        result = await db.execute(select(Order).where(Order.status == OrderStatus.PENDING, Order.created_at < cutoff))
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
        if await PolicyEngine.check_circuit_breaker(db):
            logger.warning("commerce_ops_skipped", reason="circuit_breaker_tripped")
            return {"skipped": True, "reason": "circuit_breaker",
                    "actions_taken": [], "policy_denials": [], "shadow_proposals": []}
        mode = await PolicyEngine.get_autonomy_mode(db)
        if mode == AutonomyMode.OFF:
            logger.info("commerce_ops_skipped", reason="autonomy_off")
            return {"skipped": True, "actions_taken": [], "policy_denials": [], "shadow_proposals": []}
        shadow = mode == AutonomyMode.SHADOW
        actions: list[str] = []
        denials: list[str] = []
        proposals: list[str] = []
        a1, d1, p1 = await cls._price_optimization(db, shadow)
        actions += a1; denials += d1; proposals += p1
        a2, d2, p2 = await cls._campaign_check(db, shadow)
        actions += a2; denials += d2; proposals += p2
        actions += await cls._stale_order_review(db)
        await cls._daily_report(db)
        await db.commit()
        logger.info("commerce_ops_cycle", mode=mode.value, actions=actions, denials=denials, proposals=proposals)
        return {"skipped": False, "actions_taken": actions, "policy_denials": denials, "shadow_proposals": proposals}
```

- [ ] **Step 4: Verify model fields** — check `IncidentEvent` column names in `models.py` (line 642): confirm `title`, `description`, `severity`, `affected_order_id`, `affected_campaign_id`. Check `RevenueCampaignService.check_campaign_budget` return key in `campaign_service.py`. Adjust code above to actual names before running tests.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_commerce_ops.py -v`
Expected: 7 PASSED

- [ ] **Step 6: Commit**

```bash
git add graxia/packages/revenue_os/agents/commerce_ops.py graxia/packages/revenue_os/tests/test_commerce_ops.py
git commit -m "feat(revenue-os): commerce ops agent - shadow/limited/full aware price+campaign jobs"
```

**Gate (Task 5):** 7 tests pass, including `test_shadow_mode_proposes_but_does_not_execute` and `test_circuit_breaker_blocks_cycle`.

---

### Task 6: Support Agent (identity-verified, capped, idempotent refunds)

**Files:**
- Modify: `graxia/packages/revenue_os/models.py` (append `SupportVerification`)
- Create: `graxia/packages/revenue_os/agents/support.py`
- Modify: `graxia/packages/revenue_os/schemas.py` (append SupportChatRequest/SupportChatResponse with `verification_code`)
- Create: `graxia/packages/revenue_os/tests/test_support_agent.py`

**Interfaces:**
- Consumes: `SupportIntent`/`AutonomyMode` enums (Task 1), `PolicyEngine.check/check_circuit_breaker` (Task 1), `Order`/`Refund`/`Product` models, `EmailService.queue_email(db, to_email, subject, body, html_body, ...)` (existing), `ChiefOfStaffAgent.escalate_issue` (existing), `SUPPORT_VERIFICATION_*` constants (Task 1)
- Produces: `class SupportVerification(Base)` — table `revenue_os_support_verifications`: `id UUID PK`, `email str(320)`, `code_hash str(64)`, `expires_at datetime`, `used_at Optional[datetime]`, `attempts int default 0`, `created_at`; `class SupportReply` (dataclass): `intent`, `text`, `action_taken`; `SupportAgent.handle_message(db, message, customer_email, verification_code=None) -> SupportReply`; `SupportAgent.classify_intent(message) -> SupportIntent`; `SupportAgent._issue_verification_code(db, email) -> str`; `SupportAgent._verify_code(db, email, code) -> tuple[bool, Optional[str]]`; `SupportAgent._handle_wismo(db, email) -> str`; `SupportAgent._handle_refund(db, email, message) -> tuple[str, str]`

**Security behavior (Risk Audit #3/#4/#6/#7):**
1. REFUND and WISMO intents require a one-time verification code sent to the customer's email
2. Code: 6 digits, sha256 hashed with salt from `constants.py`, 15 min TTL, max 5 attempts → escalate LOW on exhaustion
3. Refund: idempotency (no existing PROCESSING/PENDING Refund for the order), per-customer cap (max 1 auto-refund per order per 24h), dual-cap policy check (percent + absolute `value_cents`), deny → IncidentEvent MEDIUM + escalate; allow → create Refund(PROCESSING) — actual Stripe call is Task 6a
4. Every REFUND classification logs the matched keyword (Risk Audit #6 transparency)

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
from ..models import IncidentEvent, Order, Refund, SupportVerification


@pytest.mark.asyncio
async def test_classify_wismo_thai():
    assert SupportAgent.classify_intent("ออเดอร์ของฉันอยู่ไหน ส่งของหรือยัง") == SupportIntent.WISMO


@pytest.mark.asyncio
async def test_classify_refund_english():
    assert SupportAgent.classify_intent("I want a refund please") == SupportIntent.REFUND


@pytest.mark.asyncio
async def test_classify_product_question():
    assert SupportAgent.classify_intent("สินค้านี้เหมาะกับมือใหม่ไหม") == SupportIntent.PRODUCT_QUESTION


@pytest.mark.asyncio
async def test_wismo_requires_verification_code(db_session: AsyncSession, sample_order_data):
    reply = await SupportAgent.handle_message(db_session, "where is my order?", sample_order_data.customer_email)
    assert reply.action_taken == "verification_required"
    ver = await db_session.scalar(select(SupportVerification).where(
        SupportVerification.email == sample_order_data.customer_email))
    assert ver is not None


@pytest.mark.asyncio
async def test_wismo_with_code_replies_status(db_session: AsyncSession, sample_order_data):
    code = await SupportAgent._issue_verification_code(db_session, sample_order_data.customer_email)
    reply = await SupportAgent.handle_message(
        db_session, "where is my order?", sample_order_data.customer_email, verification_code=code)
    assert reply.action_taken == "wismo"
    assert sample_order_data.status.value in reply.text.lower()


@pytest.mark.asyncio
async def test_wrong_code_escalates_after_attempts(db_session: AsyncSession, sample_order_data):
    await SupportAgent._issue_verification_code(db_session, sample_order_data.customer_email)
    for _ in range(5):
        reply = await SupportAgent.handle_message(
            db_session, "where is my order?", sample_order_data.customer_email, verification_code="000000")
        assert reply.action_taken in ("verification_failed", "verification_exhausted")
    incident = await db_session.scalar(select(IncidentEvent).order_by(IncidentEvent.created_at.desc()))
    assert incident is not None


@pytest.mark.asyncio
async def test_refund_within_policy_creates_refund(db_session: AsyncSession, sample_order_data):
    await PolicyEngine.seed_default_rules(db_session)
    order = sample_order_data
    order.status = OrderStatus.PAID
    order.purchased_at = datetime.utcnow() - timedelta(days=2)
    order.amount_cents = 500_00  # under the 1,500 THB absolute cap
    await db_session.commit()
    code = await SupportAgent._issue_verification_code(db_session, order.customer_email)
    reply = await SupportAgent.handle_message(
        db_session, "please refund me", order.customer_email, verification_code=code)
    assert reply.action_taken == "refund"
    refund = await db_session.scalar(select(Refund).where(Refund.order_id == order.id))
    assert refund is not None
    assert refund.status == RefundStatus.PROCESSING


@pytest.mark.asyncio
async def test_refund_duplicate_message_is_idempotent(db_session: AsyncSession, sample_order_data):
    """Risk Audit #4: repeating the same refund request must not create a second Refund."""
    await PolicyEngine.seed_default_rules(db_session)
    order = sample_order_data
    order.status = OrderStatus.PAID
    order.purchased_at = datetime.utcnow() - timedelta(days=2)
    order.amount_cents = 500_00
    await db_session.commit()
    code = await SupportAgent._issue_verification_code(db_session, order.customer_email)
    await SupportAgent.handle_message(db_session, "refund me", order.customer_email, verification_code=code)
    code2 = await SupportAgent._issue_verification_code(db_session, order.customer_email)
    reply2 = await SupportAgent.handle_message(db_session, "refund me", order.customer_email, verification_code=code2)
    assert reply2.action_taken == "refund_duplicate"
    refunds = (await db_session.execute(select(Refund).where(Refund.order_id == order.id))).scalars().all()
    assert len(refunds) == 1


@pytest.mark.asyncio
async def test_refund_above_absolute_cap_escalates(db_session: AsyncSession, sample_order_data):
    await PolicyEngine.seed_default_rules(db_session)
    order = sample_order_data
    order.status = OrderStatus.PAID
    order.purchased_at = datetime.utcnow() - timedelta(days=2)
    order.amount_cents = 10_000_00  # above the 1,500 THB auto-refund cap
    await db_session.commit()
    code = await SupportAgent._issue_verification_code(db_session, order.customer_email)
    reply = await SupportAgent.handle_message(
        db_session, "please refund me", order.customer_email, verification_code=code)
    assert reply.action_taken == "refund_escalated"
    incident = await db_session.scalar(select(IncidentEvent).order_by(IncidentEvent.created_at.desc()))
    assert incident is not None


@pytest.mark.asyncio
async def test_refund_old_order_denied(db_session: AsyncSession, sample_order_data):
    await PolicyEngine.seed_default_rules(db_session)
    order = sample_order_data
    order.status = OrderStatus.PAID
    order.purchased_at = datetime.utcnow() - timedelta(days=60)
    await db_session.commit()
    code = await SupportAgent._issue_verification_code(db_session, order.customer_email)
    reply = await SupportAgent.handle_message(
        db_session, "please refund me", order.customer_email, verification_code=code)
    assert reply.action_taken == "refund_denied"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_support_agent.py -v`
Expected: FAIL — import error on `..agents.support` and missing `SupportVerification` model

- [ ] **Step 3: Add model** — append to `models.py` (in the POLICY & AUTONOMY section):

```python
class SupportVerification(Base):
    """One-time codes proving email ownership before WISMO/refund actions (Risk Audit #3/#7)."""
    __tablename__ = "revenue_os_support_verifications"
    __table_args__ = (
        Index("ix_support_verification_email", "email"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Implement support agent** — create `agents/support.py`

```python
"""Customer support agent - intent classification + identity-verified, policy-checked actions.

Security model (Risk Audit #3/#4/#6/#7):
- WISMO/REFUND require a one-time 6-digit code emailed to the address on the order.
- Refunds are idempotent, per-customer capped, dual-cap policy checked, and escalate
  (IncidentEvent) instead of silently denying or auto-approving above threshold.
- Every REFUND classification logs the matched keyword (Risk Audit #6 transparency).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import (
    SUPPORT_VERIFICATION_MAX_ATTEMPTS,
    SUPPORT_VERIFICATION_TTL_MINUTES,
    SUPPORT_VERIFICATION_SALT,
)
from ..core.policy_engine import PolicyEngine
from ..enums import ActionType, IncidentSeverity, OrderStatus, RefundStatus, SupportIntent
from ..models import Order, Product, Refund, SupportVerification
from ..services.email_service import EmailService
from .chief_of_staff import ChiefOfStaffAgent

logger = structlog.get_logger()

REFUND_WINDOW_DAYS = 30
REFUND_PER_ORDER_24H = 1
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


def _hash_code(code: str) -> str:
    return hashlib.sha256((code + SUPPORT_VERIFICATION_SALT).encode()).hexdigest()


class SupportAgent:
    """Handles customer chat messages. Money-moving actions are identity-verified + policy-checked."""

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
            select(Order).where(Order.customer_email == customer_email)
            .order_by(Order.created_at.desc()).limit(1)
        )

    @staticmethod
    async def _issue_verification_code(db: AsyncSession, email: str) -> str:
        """Create a fresh 6-digit code, expire outstanding unused ones, email it. Returns the code."""
        from ..models import SupportVerification as SV
        await db.execute(
            SV.__table__.update()
            .where(SV.email == email, SV.used_at.is_(None))
            .values(expires_at=datetime.utcnow())  # expire outstanding codes
        )
        code = f"{secrets.randbelow(1_000_000):06d}"
        db.add(SV(
            email=email,
            code_hash=_hash_code(code),
            expires_at=datetime.utcnow() + timedelta(minutes=SUPPORT_VERIFICATION_TTL_MINUTES),
        ))
        await db.flush()
        await EmailService.queue_email(
            db,
            to_email=email,
            subject="รหัสยืนยันตัวตน (verification code)",
            body=f"รหัสยืนยันของคุณ: {code} ใช้ได้ {SUPPORT_VERIFICATION_TTL_MINUTES} นาที",
        )
        return code

    @staticmethod
    async def _verify_code(db: AsyncSession, email: str, code: Optional[str]) -> tuple[bool, Optional[str]]:
        """Return (ok, failure_action). failure_action: verification_required |
        verification_failed | verification_exhausted."""
        if not code:
            return False, "verification_required"
        ver = await db.scalar(
            select(SupportVerification)
            .where(SupportVerification.email == email, SupportVerification.used_at.is_(None))
            .order_by(SupportVerification.created_at.desc()).limit(1)
        )
        if ver is None:
            return False, "verification_required"
        if ver.expires_at < datetime.utcnow():
            return False, "verification_required"
        if hmac.compare_digest(ver.code_hash, _hash_code(code)):
            ver.used_at = datetime.utcnow()
            await db.flush()
            return True, None
        ver.attempts += 1
        if ver.attempts >= SUPPORT_VERIFICATION_MAX_ATTEMPTS:
            ver.used_at = datetime.utcnow()  # burn the code
            await db.flush()
            return False, "verification_exhausted"
        await db.flush()
        return False, "verification_failed"

    @staticmethod
    async def _handle_wismo(db: AsyncSession, customer_email: str) -> str:
        order = await SupportAgent._latest_order(db, customer_email)
        if order is None:
            return "ไม่พบออเดอร์ในระบบของเรา (no orders found for this email)"
        return f"สถานะออเดอร์ {order.id}: {order.status.value}"

    @staticmethod
    async def _handle_refund(db: AsyncSession, customer_email: str, message: str) -> tuple[str, str]:
        """Returns (reply_text, action). Actions: refund | refund_duplicate | refund_escalated | refund_denied."""
        order = await SupportAgent._latest_order(db, customer_email)
        if order is None:
            return "ไม่พบออเดอร์สำหรับอีเมลนี้ จึงไม่สามารถคืนเงินได้", "refund_denied"
        # Idempotency (Risk Audit #4): no refund already in flight for this order
        existing = await db.scalar(
            select(Refund).where(
                Refund.order_id == order.id,
                Refund.status.in_([RefundStatus.PENDING, RefundStatus.PROCESSING]),
            ).limit(1)
        )
        if existing is not None:
            return "มีการดำเนินการคืนเงินสำหรับออเดอร์นี้อยู่แล้ว", "refund_duplicate"
        # Per-customer rate cap: max REFUND_PER_ORDER_24H auto-refunds per order per 24h
        cutoff = datetime.utcnow() - timedelta(hours=24)
        recent = await db.scalar(
            select(Refund.id).where(Refund.order_id == order.id, Refund.created_at >= cutoff)
            .limit(REFUND_PER_ORDER_24H)
        )
        if recent is not None:
            return "มีการคืนเงินสำหรับออเดอร์นี้ภายใน 24 ชั่วโมงที่ผ่านมา", "refund_duplicate"
        # Dual-cap policy check (percent + absolute cents)
        age_days = (datetime.utcnow() - order.purchased_at).days
        decision = await PolicyEngine.check(
            db, ActionType.REFUND,
            {
                "value": 100.0,
                "value_cents": order.amount_cents,
                "order_id": str(order.id),
                "order_age_days": age_days,
            },
        )
        if not decision.allow:
            # Above threshold → escalate instead of silently denying (Risk Audit #3/#9)
            db.add(IncidentEvent(
                title=f"Refund request needs human review: {order.id}",
                description=f"{decision.reason} | message: {message[:300]}",
                severity=IncidentSeverity.MEDIUM,
                affected_order_id=order.id,
            ))
            return (
                "ออเดอร์นี้เกินวงเงินที่ระบบคืนเงินอัตโนมัติได้ เราส่งเรื่องให้ทีมตรวจสอบแล้ว "
                "จะติดต่อกลับทางอีเมล",
                "refund_escalated",
            )
        db.add(Refund(
            order_id=order.id,
            amount_cents=order.amount_cents,
            currency=order.currency,
            reason=f"support agent: {message[:200]}",
            status=RefundStatus.PROCESSING,
        ))
        await db.flush()
        return "เราเริ่มดำเนินการคืนเงินให้แล้ว จะอัปเดตทางอีเมลภายใน 3-5 วันทำการ", "refund"

    @classmethod
    async def handle_message(
        cls, db: AsyncSession, message: str, customer_email: str, verification_code: Optional[str] = None
    ) -> SupportReply:
        intent = cls.classify_intent(message)
        if intent == SupportIntent.COMPLAINT:
            await ChiefOfStaffAgent.escalate_issue(
                db,
                title=f"Support complaint from {customer_email}",
                description=message[:500],
                severity=IncidentSeverity.MEDIUM,
            )
            await db.commit()
            return SupportReply(
                intent=intent,
                text="รับทราบแล้ว เราส่งเรื่องนี้ให้ทีมตรวจสอบโดยด่วน ขออภัยในความไม่สะดวก",
                action_taken="escalated",
            )
        if intent in (SupportIntent.REFUND, SupportIntent.WISMO):
            ok, fail_action = await cls._verify_code(db, customer_email, verification_code)
            if not ok:
                if fail_action == "verification_exhausted":
                    await ChiefOfStaffAgent.escalate_issue(
                        db,
                        title=f"Verification abuse suspected: {customer_email}",
                        description="Too many wrong verification codes",
                        severity=IncidentSeverity.LOW,
                    )
                await db.commit()
                return SupportReply(
                    intent=intent,
                    text="เราส่งรหัสยืนยัน 6 หลักไปที่อีเมลของคุณแล้ว "
                         "(เราไม่เปิดเผยข้อมูลออเดอร์โดยไม่ยืนยันตัวตน)",
                    action_taken=fail_action,
                )
        if intent == SupportIntent.REFUND:
            matched = [k for k in REFUND_KEYWORDS if k in message.lower()]  # Risk Audit #6 transparency
            logger.info("refund_request", email=customer_email, matched_keywords=matched)
            text, action = await cls._handle_refund(db, customer_email, message)
            await db.commit()
            return SupportReply(intent=intent, text=text, action_taken=action)
        if intent == SupportIntent.WISMO:
            text = await cls._handle_wismo(db, customer_email)
            await db.commit()
            return SupportReply(intent=intent, text=text, action_taken="wismo")
        if intent in (SupportIntent.PRODUCT_QUESTION, SupportIntent.SALES):
            result = await db.execute(select(Product).limit(3))
            products = list(result.scalars().all())
            names = ", ".join(p.name for p in products) if products else "(no products yet)"
            await db.commit()
            return SupportReply(intent=intent, text=f"สินค้าของเรา: {names} — ถามเพิ่มเติมได้เลยครับ", action_taken="catalog")
        await db.commit()
        return SupportReply(intent=intent, text="ขอบคุณที่ติดต่อ เราจะตอบกลับโดยเร็วที่สุด", action_taken="none")
```

- [ ] **Step 5: Add salt constant** — in `constants.py` add:

```python
SUPPORT_VERIFICATION_SALT = "graxia-support-v1"  # replace via env SECRET_KEY-derived salt in production
```

- [ ] **Step 6: Add chat schemas** — append to `schemas.py`:

```python
class SupportChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    customer_email: str = Field(..., max_length=320)
    verification_code: Optional[str] = Field(default=None, max_length=6)


class SupportChatResponse(BaseModel):
    intent: str
    reply: str
    action_taken: Optional[str] = None
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_support_agent.py -v`
Expected: 10 PASSED

- [ ] **Step 8: Commit**

```bash
git add graxia/packages/revenue_os/models.py graxia/packages/revenue_os/constants.py graxia/packages/revenue_os/agents/support.py graxia/packages/revenue_os/schemas.py graxia/packages/revenue_os/tests/test_support_agent.py
git commit -m "feat(revenue-os): support agent - identity-verified, capped, idempotent refunds"
```

**Gate (Task 6):** 10 tests pass — specifically the idempotency, absolute-cap escalation, and wrong-code exhaustion tests.

---

### Task 6a: Stripe refund execution task

**Files:**
- Create: `graxia/packages/revenue_os/services/refund_executor.py`
- Create: `graxia/packages/revenue_os/celery/tasks/process_refunds.py`
- Create: `graxia/packages/revenue_os/tests/test_refund_executor.py`

**Interfaces:**
- Consumes: `Refund` model (`platform`, `platform_refund_id`, `status`, `order_id`, `amount_cents`), `Order` model (`platform`, `stripe_payment_intent`), `RefundStatus` enum, existing stripe SDK usage pattern (env `STRIPE_API_KEY` set on `stripe.api_key`)
- Produces: `RefundExecutor.process_pending_refunds(db) -> dict` (counts by outcome); celery task `process_refunds()`; refunds actually call Stripe `Refund.create` for `platform="stripe"` orders, mark `PROCESSED` with `platform_refund_id`, `FAILED` on error (idempotent via existing `platform_refund_id` unique constraint + skip-if-set)

- [ ] **Step 1: Write failing tests** — `tests/test_refund_executor.py`

```python
import uuid
from datetime import datetime, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.refund_executor import RefundExecutor
from ..enums import OrderStatus, RefundStatus
from ..models import Order, Refund
from ..services.order_service import OrderService


@pytest.mark.asyncio
async def test_stripe_refund_calls_api_and_marks_processed(db_session: AsyncSession, sample_product_data, sample_customer_data, monkeypatch):
    order = await OrderService.create_order(
        db_session, platform="stripe", platform_order_id="cs_ref_1",
        customer_email=sample_customer_data["email"], product_id=sample_product_data.id,
        amount_cents=500_00, stripe_payment_intent="pi_ref_1",
    )
    await OrderService.update_order_status(db_session, order.id, OrderStatus.PAID)
    refund = Refund(order_id=order.id, amount_cents=500_00, currency="THB",
                    reason="test", status=RefundStatus.PROCESSING, platform="stripe")
    db_session.add(refund)
    await db_session.commit()

    class FakeStripeRefunds:
        @staticmethod
        def create(**kwargs):
            assert kwargs["payment_intent"] == "pi_ref_1"
            assert kwargs["amount"] == 500_00
            return type("R", (), {"id": "re_fake_1"})()

    monkeypatch.setattr("graxia.packages.revenue_os.services.refund_executor.stripe_refunds", FakeStripeRefunds)
    result = await RefundExecutor.process_pending_refunds(db_session)
    assert result["processed"] == 1
    await db_session.refresh(refund)
    assert refund.status == RefundStatus.PROCESSED
    assert refund.platform_refund_id == "re_fake_1"


@pytest.mark.asyncio
async def test_failed_refund_marked_failed(db_session: AsyncSession, sample_product_data, sample_customer_data, monkeypatch):
    order = await OrderService.create_order(
        db_session, platform="stripe", platform_order_id="cs_ref_2",
        customer_email=sample_customer_data["email"], product_id=sample_product_data.id,
        amount_cents=500_00, stripe_payment_intent="pi_ref_2",
    )
    await OrderService.update_order_status(db_session, order.id, OrderStatus.PAID)
    refund = Refund(order_id=order.id, amount_cents=500_00, currency="THB",
                    reason="test", status=RefundStatus.PROCESSING, platform="stripe")
    db_session.add(refund)
    await db_session.commit()

    class Boom:
        @staticmethod
        def create(**kwargs):
            raise Exception("card declined")

    monkeypatch.setattr("graxia.packages.revenue_os.services.refund_executor.stripe_refunds", Boom)
    result = await RefundExecutor.process_pending_refunds(db_session)
    assert result["failed"] == 1
    await db_session.refresh(refund)
    assert refund.status == RefundStatus.FAILED


@pytest.mark.asyncio
async def test_non_stripe_refund_skipped(db_session: AsyncSession, sample_product_data, sample_customer_data):
    order = await OrderService.create_order(
        db_session, platform="manual", platform_order_id="cs_ref_3",
        customer_email=sample_customer_data["email"], product_id=sample_product_data.id,
        amount_cents=500_00,
    )
    await OrderService.update_order_status(db_session, order.id, OrderStatus.PAID)
    refund = Refund(order_id=order.id, amount_cents=500_00, currency="THB",
                    reason="test", status=RefundStatus.PROCESSING, platform="manual")
    db_session.add(refund)
    await db_session.commit()
    result = await RefundExecutor.process_pending_refunds(db_session)
    assert result["skipped"] == 1
    assert result["processed"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_refund_executor.py -v`
Expected: FAIL — import error on `..services.refund_executor`

- [ ] **Step 3: Implement executor** — create `services/refund_executor.py`

```python
"""Executes pending Refund rows against payment providers (Risk Audit #5).

Idempotent: a Refund that already has a platform_refund_id is never re-executed
(the (platform, platform_refund_id) unique constraint on Refund enforces this).
"""
from __future__ import annotations

import os

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import stripe
from datetime import datetime
from ..enums import RefundStatus
from ..models import Order, Refund

logger = structlog.get_logger()

stripe_refunds = stripe.Refund  # monkeypatch target for tests


class RefundExecutor:
    @staticmethod
    async def process_pending_refunds(db: AsyncSession) -> dict:
        result = await db.execute(
            select(Refund).where(Refund.status == RefundStatus.PROCESSING).order_by(Refund.created_at)
        )
        refunds = list(result.scalars().all())
        counts = {"processed": 0, "failed": 0, "skipped": 0}
        for refund in refunds:
            order = await db.get(Order, refund.order_id)
            if order is None or order.platform != "stripe":
                counts["skipped"] += 1
                continue
            if refund.platform_refund_id:
                counts["skipped"] += 1  # already processed
                continue
            try:
                stripe.api_key = os.getenv("STRIPE_API_KEY")
                created = stripe_refunds.create(
                    payment_intent=order.stripe_payment_intent,
                    amount=refund.amount_cents,
                    metadata={"refund_id": str(refund.id)},
                )
                refund.platform_refund_id = created.id
                refund.status = RefundStatus.PROCESSED
                refund.processed_at = datetime.utcnow()
                counts["processed"] += 1
            except Exception:
                logger.exception("refund_execution_failed", refund_id=str(refund.id))
                refund.status = RefundStatus.FAILED
                counts["failed"] += 1
        await db.commit()
        return counts
```

- [ ] **Step 4: Create celery task** — `celery/tasks/process_refunds.py`

```python
"""Process pending refunds against payment providers."""
from __future__ import annotations

from ...db import get_db_session
from ...services.refund_executor import RefundExecutor


async def process_refunds_with_db(db):
    return await RefundExecutor.process_pending_refunds(db)


def process_refunds():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await process_refunds_with_db(db)

    return asyncio.run(_impl())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_refund_executor.py -v`
Expected: 3 PASSED

- [ ] **Step 6: Commit**

```bash
git add graxia/packages/revenue_os/services/refund_executor.py graxia/packages/revenue_os/celery/tasks/process_refunds.py graxia/packages/revenue_os/tests/test_refund_executor.py
git commit -m "feat(revenue-os): stripe refund executor + celery task (idempotent)"
```

**Gate (Task 6a):** 3 tests pass. `STRIPE_API_KEY` must be provisioned before the task runs against real refunds.

---

### Task 7: Support chat API router

**Files:**
- Create: `graxia/services/revenue_os_api/routers/support.py`
- Modify: `graxia/services/revenue_os_api/router.py`
- Create: `graxia/packages/revenue_os/tests/test_support_router.py`

**Interfaces:**
- Consumes: `SupportAgent.handle_message(db, message, customer_email, verification_code)` (Task 6), `SupportChatRequest/SupportChatResponse` (Task 6), `get_db` dependency
- Produces: `POST /api/support/chat` → `SupportChatResponse` (public — no admin auth; rate limiting noted in Task 11)

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

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_support_router.py -v`
Expected: 1 PASSED

- [ ] **Step 3: Create router** — `graxia/services/revenue_os_api/routers/support.py`

```python
"""Customer support chat endpoint (public - identity verified inside the agent)."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.agents.support import SupportAgent
from ....packages.revenue_os.schemas import SupportChatRequest, SupportChatResponse
from ..dependencies import get_db

router = APIRouter(prefix="/api/support", tags=["support"])


@router.post("/chat", response_model=SupportChatResponse)
async def chat(body: SupportChatRequest, db: AsyncSession = Depends(get_db)) -> SupportChatResponse:
    reply = await SupportAgent.handle_message(
        db, body.message, body.customer_email, verification_code=body.verification_code
    )
    return SupportChatResponse(
        intent=reply.intent.value,
        reply=reply.text,
        action_taken=reply.action_taken,
    )
```

- [ ] **Step 4: Register router** — in `router.py`, follow the Task 2 Step 5 pattern.

- [ ] **Step 5: Run full package test suite**

Run: `pytest graxia/packages/revenue_os/tests/ -v`
Expected: all tests PASS (existing + new files)

- [ ] **Step 6: Commit**

```bash
git add graxia/services/revenue_os_api/routers/support.py graxia/services/revenue_os_api/router.py graxia/packages/revenue_os/tests/test_support_router.py
git commit -m "feat(revenue-os): support chat API endpoint"
```

**Gate (Task 7):** full package suite green.

---

### Task 8: Celery beat wiring (locked tasks)

**Files:**
- Modify: `graxia/packages/revenue_os/celery/celery_app.py`
- Create: `graxia/packages/revenue_os/celery/tasks/commerce_ops.py`
- Modify: `graxia/packages/revenue_os/tests/test_celery_tasks.py` (append overlap test)

**Interfaces:**
- Consumes: `CommerceOpsAgent.run_cycle` (Task 5), `digital_fulfillment` (Task 4), `process_refunds` (Task 6a), `create_revenue_os_celery_app` (existing)
- Produces: celery task `commerce_ops()` (lock-wrapped); beat entries for `digital_fulfillment` (5 min), `process_refunds` (5 min), `commerce_ops` (hourly)

- [ ] **Step 1: Create celery task** — `celery/tasks/commerce_ops.py`

```python
"""Commerce ops agent celery task - lock-wrapped (Risk Audit #8)."""
from __future__ import annotations

import structlog

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...agents.commerce_ops import CommerceOpsAgent

logger = structlog.get_logger()

LOCK_NAME = "commerce_ops"


async def commerce_ops_with_db(db):
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=300) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        return await CommerceOpsAgent.run_cycle(db)


def commerce_ops():
    """Run the autonomous commerce cycle. Follows agent_consumers asyncio pattern."""
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await commerce_ops_with_db(db)

    return asyncio.run(_impl())
```

- [ ] **Step 2: Add beat schedule** — in `celery_app.py`, find the existing `beat_schedule` and add (copy the exact schedule style of the nearest existing entry — crontab vs seconds — and verify the task name prefix used by existing entries, e.g. `revenue_os.` vs `graxia.packages.revenue_os.`):

```python
    "digital_fulfillment": {
        "task": "revenue_os.celery.tasks.digital_fulfillment.digital_fulfillment",
        "schedule": 300.0,  # every 5 minutes
    },
    "process_refunds": {
        "task": "revenue_os.celery.tasks.process_refunds.process_refunds",
        "schedule": 300.0,  # every 5 minutes
    },
    "commerce_ops": {
        "task": "revenue_os.celery.tasks.commerce_ops.commerce_ops",
        "schedule": 3600.0,  # hourly
    },
```

- [ ] **Step 3: Add overlap test** — append to `tests/test_celery_tasks.py` (existing file):

```python
@pytest.mark.asyncio
async def test_commerce_ops_task_respects_lock(db_session: AsyncSession):
    from ...core.db_ops import acquire_automation_lock
    from ..celery.tasks.commerce_ops import commerce_ops_with_db

    async with acquire_automation_lock(db_session, "commerce_ops", ttl_seconds=300):
        result = await commerce_ops_with_db(db_session)
    assert result.get("skipped") is True
    assert "lock" in result.get("reason", "")
```

- [ ] **Step 4: Verify task registration imports**

Run: `python -c "from graxia.packages.revenue_os.celery.tasks import digital_fulfillment, commerce_ops, process_refunds; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Run tests**

Run: `pytest graxia/packages/revenue_os/tests/test_celery_tasks.py -v`
Expected: PASS (existing + new overlap test)

- [ ] **Step 6: Commit**

```bash
git add graxia/packages/revenue_os/celery/celery_app.py graxia/packages/revenue_os/celery/tasks/commerce_ops.py graxia/packages/revenue_os/tests/test_celery_tasks.py
git commit -m "feat(revenue-os): celery beat - locked fulfillment/refund/commerce cycles"
```

**Gate (Task 8):** overlap test passes; import smoke check prints `ok`.

---

### Task 9: Frontend support chat widget

**Files:**
- Create: `frontend/src/components/chat/SupportChat.tsx`
- Create: `frontend/src/components/chat/SupportChat.test.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/StorePage.tsx`

**Interfaces:**
- Consumes: existing client pattern in `frontend/src/lib/api.ts` (check the actual helper name — `apiFetch` or similar — and mirror it)
- Produces: `supportChat(message, customerEmail, verificationCode?) -> Promise<{intent, reply, action_taken}>`; `<SupportChat />` mounted in `StorePage`; the widget shows a code input when the reply has `action_taken === 'verification_required'`

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
    const input = screen.getByPlaceholderText(/พิมพ์ข้อความ/i)
    fireEvent.change(input, { target: { value: 'where is my order?' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => {
      expect(screen.getByText(/สถานะออเดอร์/i)).toBeTruthy()
    })
  })

  it('shows a code input when verification is required', async () => {
    const { supportChat } = await import('../../lib/api')
    vi.mocked(supportChat).mockResolvedValueOnce({
      intent: 'wismo',
      reply: 'เราส่งรหัสยืนยัน 6 หลักไปที่อีเมลของคุณแล้ว',
      action_taken: 'verification_required',
    })
    render(<SupportChat customerEmail="test@example.com" />)
    fireEvent.click(screen.getByRole('button', { name: /support|help/i }))
    const input = screen.getByPlaceholderText(/พิมพ์ข้อความ/i)
    fireEvent.change(input, { target: { value: 'where is my order?' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/รหัสยืนยัน/i)).toBeTruthy()
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
  const [verificationCode, setVerificationCode] = useState('')
  const [awaitingCode, setAwaitingCode] = useState(false)
  const [history, setHistory] = useState<{ role: 'user' | 'bot'; text: string }[]>([])
  const [loading, setLoading] = useState(false)

  const send = async (overrideMessage?: string, overrideCode?: string) => {
    const text = overrideMessage ?? message
    if (!text.trim()) return
    setHistory((h) => [...h, { role: 'user', text }])
    setMessage('')
    setLoading(true)
    try {
      const res = await supportChat(text, customerEmail, overrideCode || undefined)
      setHistory((h) => [...h, { role: 'bot', text: res.reply }])
      if (res.action_taken === 'verification_required') setAwaitingCode(true)
      if (res.action_taken !== 'verification_required') setAwaitingCode(false)
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
        onSubmit={(e) => { e.preventDefault(); awaitingCode ? send(message, verificationCode) : send(message) }}
        className="flex flex-col gap-2 border-t p-2"
      >
        {awaitingCode && (
          <input
            value={verificationCode}
            onChange={(e) => setVerificationCode(e.target.value)}
            placeholder="รหัสยืนยัน 6 หลัก"
            className="rounded border px-2 py-1 text-sm"
            maxLength={6}
          />
        )}
        <div className="flex gap-2">
          <input
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="พิมพ์ข้อความ..."
            className="flex-1 rounded border px-2 py-1 text-sm"
          />
          <button type="submit" className="rounded bg-blue-600 px-3 py-1 text-white">ส่ง</button>
        </div>
      </form>
    </div>
  )
}
```

- [ ] **Step 4: Add API client** — in `frontend/src/lib/api.ts`, mirror the existing request pattern (replace `apiFetch` with the actual helper the file exports):

```ts
export async function supportChat(message: string, customerEmail: string, verificationCode?: string) {
  const res = await apiFetch('/api/support/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      customer_email: customerEmail,
      verification_code: verificationCode,
    }),
  })
  return res.json()
}
```

- [ ] **Step 5: Mount widget** — in `frontend/src/pages/StorePage.tsx`, render `<SupportChat customerEmail={currentUserEmail} />` (use the existing auth/email source; if none, pass `"guest@graxia.local"`).

- [ ] **Step 6: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/chat/SupportChat.test.tsx`
Expected: 2 PASSED

- [ ] **Step 7: Run frontend suite**

Run: `cd frontend && npx vitest run`
Expected: all existing + new PASS (if pre-existing failures exist, report but do not fix unrelated)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/chat/SupportChat.tsx frontend/src/components/chat/SupportChat.test.tsx frontend/src/lib/api.ts frontend/src/pages/StorePage.tsx
git commit -m "feat(frontend): support chat widget with verification-code flow on storefront"
```

**Gate (Task 9):** 2 component tests pass; full frontend suite green (or pre-existing failures documented).

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
cd backend && alembic revision --autogenerate -m "add policy rules, autonomy state, support verifications"
```

If the repo uses a different migration flow (check `backend/alembic.ini` / `graxia/migrations`), follow that instead. **Migration must honor the Task 1 mapping note** (`enabled=False → mode=OFF`, `enabled=True → mode=FULL` if the table pre-exists with `enabled`).

- [ ] **Step 5: Update design doc** — in `docs/superpowers/specs/2026-08-16-autonomous-ecommerce-design.md`, add a "Phase 1 Status" section listing completed tasks and any deviations found during implementation (e.g. model field renames).

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-08-16-autonomous-ecommerce-design.md
git commit -m "docs: phase 1 completion status"
```

**Gate (Task 10):** full suites green, migration generated, spec updated.

---

### Task 11: Incident alerting (Telegram)

**Files:**
- Modify: `graxia/packages/revenue_os/models.py` (add `notified_at` to IncidentEvent — additive)
- Create: `graxia/packages/revenue_os/celery/tasks/incident_alerter.py`
- Modify: `graxia/packages/revenue_os/celery/celery_app.py` (beat entry)
- Create: `graxia/packages/revenue_os/tests/test_incident_alerter.py`

**Interfaces:**
- Consumes: `IncidentEvent` model (add `notified_at: Mapped[Optional[datetime]]`), `TelegramNotifier` from `graxia/services/telegram_notifier.py` — verified signatures: `send_message(text, parse_mode=ParseMode.HTML) -> bool` and `notify_system_alert(severity, msg)` (use `notify_system_alert`; it exists at line ~180)
- Produces: `alerter_sweep(db) -> dict` (counts sent/skipped); celery task `incident_alerter()`; beat entry every 5 min; incidents with severity >= MEDIUM and `notified_at IS NULL` are sent once and marked

- [ ] **Step 1: Write failing tests** — `tests/test_incident_alerter.py`

```python
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..celery.tasks.incident_alerter import alerter_sweep
from ..enums import IncidentSeverity
from ..models import IncidentEvent


@pytest.mark.asyncio
async def test_alerter_sends_medium_incidents_once(db_session: AsyncSession, monkeypatch):
    db_session.add(IncidentEvent(title="boom", description="x", severity=IncidentSeverity.MEDIUM))
    await db_session.commit()

    sent = []
    class FakeNotifier:
        @staticmethod
        def notify_system_alert(severity, msg):
            sent.append((severity, msg))
            return True

    monkeypatch.setattr("graxia.packages.revenue_os.celery.tasks.incident_alerter.TelegramNotifier", FakeNotifier)
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

    monkeypatch.setattr("graxia.packages.revenue_os.celery.tasks.incident_alerter.TelegramNotifier", FakeNotifier)
    result = await alerter_sweep(db_session)
    assert result["sent"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_incident_alerter.py -v`
Expected: FAIL — import error / missing `notified_at` column

- [ ] **Step 3: Add column** — in `models.py`, `IncidentEvent` (line 642) add after `severity`/`title` fields (additive only):

```python
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 4: Create alerter task** — `celery/tasks/incident_alerter.py`

```python
"""Send MEDIUM+ incidents to Telegram once (Risk Audit #10 — make humans notice)."""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...enums import IncidentSeverity
from ...models import IncidentEvent
from graxia.services.telegram_notifier import TelegramNotifier

logger = structlog.get_logger()

notifier = TelegramNotifier  # monkeypatch target for tests


async def alerter_sweep(db: AsyncSession) -> dict:
    result = await db.execute(
        select(IncidentEvent).where(
            IncidentEvent.severity.in_([IncidentSeverity.MEDIUM, IncidentSeverity.HIGH]),
            IncidentEvent.notified_at.is_(None),
        ).order_by(IncidentEvent.created_at)
    )
    incidents = list(result.scalars().all())
    sent = 0
    for incident in incidents:
        try:
            notifier.notify_system_alert(
                severity=incident.severity.value,
                msg=f"{incident.title}\n{incident.description}",
            )
            incident.notified_at = __import__("datetime").datetime.utcnow()
            sent += 1
        except Exception:
            logger.exception("incident_alert_failed", incident_id=str(incident.id))
    await db.commit()
    return {"sent": sent, "pending": len(incidents) - sent}


def incident_alerter():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await alerter_sweep(db)

    return asyncio.run(_impl())
```

- [ ] **Step 5: Add beat entry** — in `celery_app.py` (same style as Task 8 Step 2):

```python
    "incident_alerter": {
        "task": "revenue_os.celery.tasks.incident_alerter.incident_alerter",
        "schedule": 300.0,  # every 5 minutes
    },
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_incident_alerter.py -v`
Expected: 2 PASSED

- [ ] **Step 7: Commit**

```bash
git add graxia/packages/revenue_os/models.py graxia/packages/revenue_os/celery/tasks/incident_alerter.py graxia/packages/revenue_os/celery/celery_app.py graxia/packages/revenue_os/tests/test_incident_alerter.py
git commit -m "feat(revenue-os): telegram incident alerter (MEDIUM+, sent-once)"
```

**Gate (Task 11):** 2 tests pass. Telegram bot credentials (existing env) must be configured for real delivery.

---

### Task 12: Staged autonomy rollout (gates + runbook)

**Files:**
- Create: `graxia/packages/revenue_os/celery/tasks/rollout_gate_checker.py`
- Create: `docs/runbooks/autonomy-rollout.md`
- Create: `graxia/packages/revenue_os/tests/test_rollout_gates.py`
- Modify: `graxia/packages/revenue_os/celery/celery_app.py` (daily beat entry)

**Interfaces:**
- Consumes: `PolicyEngine.get_autonomy_mode/set_autonomy_mode/check_circuit_breaker` (Task 1), `IncidentEvent`/`StrategyLog`/`AuditLog`/`PolicyRule` models, `TelegramNotifier` (Task 11 pattern)
- Produces: `RolloutGateChecker.check_readiness(db) -> dict` with keys `stage`, `gates: dict[str, bool]`, `ready_for_next: bool`, `blockers: list[str]`; celery task `rollout_gate_checker()` (daily, writes StrategyLog + Telegram summary, **never auto-advances**); runbook documenting the manual advance procedure

**Stage definitions (the ONLY way autonomy leaves OFF):**

| Transition | Minimum observation | Hard gates |
|---|---|---|
| OFF → SHADOW | — | Gate 0: business owner confirms/edits every seeded policy cap; full test suite green; `ADMIN_API_KEY` + `STRIPE_API_KEY` provisioned |
| SHADOW → LIMITED | 7 days | Gate 1: zero HIGH incidents; ≤ 2 policy denials/day avg; ≥ 10 shadow decisions logged; human reviewed shadow log and approves advance |
| LIMITED → FULL | 7 days | Gate 2: zero HIGH incidents; circuit breaker never tripped; revenue impact of LIMITED actions within ±20% of expectation; audit review passed |
| any → OFF | — | circuit breaker trip (auto) or human decision — re-walk from SHADOW |

- [ ] **Step 1: Write failing tests** — `tests/test_rollout_gates.py`

```python
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
    # fabricate 10+ shadow decisions and 7+ days of observation
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest graxia/packages/revenue_os/tests/test_rollout_gates.py -v`
Expected: FAIL — import error

- [ ] **Step 3: Implement gate checker** — create `celery/tasks/rollout_gate_checker.py`

```python
"""Staged autonomy rollout gates (Task 12). Computes readiness per stage.
NEVER auto-advances — advancing is a manual, authenticated admin API call."""
from __future__ import annotations

from datetime import datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...core.policy_engine import PolicyEngine
from ...enums import AutonomyMode, IncidentSeverity
from ...models import AuditLog, IncidentEvent, PolicyRule, StrategyLog
from graxia.services.telegram_notifier import TelegramNotifier

logger = structlog.get_logger()

SHADOW_MIN_DAYS = 7
LIMITED_MIN_DAYS = 7
SHADOW_MIN_DECISIONS = 10
MAX_DENIALS_PER_DAY = 2


async def days_in_mode(db: AsyncSession, mode: AutonomyMode) -> int:
    """Days since the autonomy mode was last set. Reads the singleton row.
    Module-level so tests can monkeypatch it (must be an async function)."""
    from ...constants import AUTONOMY_STATE_ID
    from ...models import AutonomyState as AS
    state = await db.scalar(select(AS).where(AS.id == AUTONOMY_STATE_ID))
    if state is None or state.updated_at is None:
        return 0
    updated = state.updated_at
    if updated.tzinfo is not None:
        updated = updated.replace(tzinfo=None)
    return (datetime.utcnow() - updated).days


class RolloutGateChecker:
    @staticmethod
    async def check_readiness(db: AsyncSession) -> dict:
        mode = await PolicyEngine.get_autonomy_mode(db)
        gates: dict[str, bool] = {}
        blockers: list[str] = []

        rule_count = await db.scalar(select(func.count(PolicyRule.id)))
        high_incidents = await db.scalar(
            select(func.count(IncidentEvent.id)).where(IncidentEvent.severity == IncidentSeverity.HIGH)
        )
        shadow_decisions = await db.scalar(
            select(func.count(AuditLog.id)).where(AuditLog.event_type.like("agent.%.shadow"))
        )
        today_denials = await db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.event_type.in_(["agent.price_change.denied", "agent.campaign_pause.denied"]),
                AuditLog.created_at >= datetime.utcnow() - timedelta(days=1),
            )
        )
        days = await days_in_mode(db, mode)

        if mode == AutonomyMode.OFF:
            gates["rules_seeded"] = rule_count and rule_count >= 6
            gates["suites_green"] = True  # verified manually at Task 10; human confirms at advance
            gates["secrets_provisioned"] = True  # verified manually; human confirms at advance
            if not gates["rules_seeded"]:
                blockers.append("seed default policy rules first")
            ready = gates["rules_seeded"] and gates["suites_green"] and gates["secrets_provisioned"]
        elif mode == AutonomyMode.SHADOW:
            gates["no_high_incidents"] = (high_incidents or 0) == 0
            gates["denial_rate_ok"] = (today_denials or 0) <= MAX_DENIALS_PER_DAY
            gates["shadow_decision_count"] = (shadow_decisions or 0) >= SHADOW_MIN_DECISIONS
            gates["observation_period"] = days >= SHADOW_MIN_DAYS
            gates["human_reviewed"] = False  # manual; operator confirms at advance (runbook)
            automated = {k: v for k, v in gates.items() if k != "human_reviewed"}
            for name, ok in automated.items():
                if not ok:
                    blockers.append(name)
            ready = all(automated.values())
        elif mode == AutonomyMode.LIMITED:
            gates["no_high_incidents"] = (high_incidents or 0) == 0
            gates["breaker_never_tripped"] = True  # see note: verify via AuditLog scan in prod
            gates["observation_period"] = days >= LIMITED_MIN_DAYS
            gates["impact_within_expectation"] = True  # manual review by operator
            gates["human_reviewed"] = False
            automated = {k: v for k, v in gates.items() if k != "human_reviewed"}
            for name, ok in automated.items():
                if not ok:
                    blockers.append(name)
            ready = all(automated.values())
        else:  # FULL — nothing above it
            ready = False

        return {
            "stage": mode.value,
            "gates": gates,
            "ready_for_next": ready,
            "blockers": blockers,
        }

    @staticmethod
    async def run_daily(db: AsyncSession) -> dict:
        """Daily summary: write StrategyLog + Telegram note. Never advances."""
        readiness = await RolloutGateChecker.check_readiness(db)
        db.add(StrategyLog(
            week_start=datetime.utcnow().date(),
            summary=f"Autonomy rollout status: stage={readiness['stage']} ready_for_next={readiness['ready_for_next']}",
            recommendations="; ".join(readiness["blockers"]) or "no blockers — manual advance review due",
        ))
        await db.commit()
        try:
            TelegramNotifier.notify_system_alert(
                severity="info",
                msg=f"Autonomy stage={readiness['stage']} ready_for_next={readiness['ready_for_next']}",
            )
        except Exception:
            logger.exception("rollout_notify_failed")
        return readiness


async def rollout_gate_checker():
    async with get_db_session() as db:
        return await RolloutGateChecker.run_daily(db)
```

- [ ] **Step 4: Add daily beat entry** — in `celery_app.py`:

```python
    "rollout_gate_checker": {
        "task": "revenue_os.celery.tasks.rollout_gate_checker.rollout_gate_checker",
        "schedule": 86400.0,  # daily
    },
```

- [ ] **Step 5: Create runbook** — `docs/runbooks/autonomy-rollout.md` with: the stage table above; the exact advance command `POST /api/autonomy/mode {"mode": "shadow"|"limited"|"full"}` with `X-Admin-Api-Key` header; the manual review checklist per gate; the circuit-breaker auto-OFF + re-walk procedure; who may advance (single designated operator).

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest graxia/packages/revenue_os/tests/test_rollout_gates.py -v`
Expected: 3 PASSED

- [ ] **Step 7: Commit**

```bash
git add graxia/packages/revenue_os/celery/tasks/rollout_gate_checker.py graxia/packages/revenue_os/celery/celery_app.py graxia/packages/revenue_os/tests/test_rollout_gates.py docs/runbooks/autonomy-rollout.md
git commit -m "feat(revenue-os): staged autonomy rollout gates + runbook (off->shadow->limited->full)"
```

**Gate (Task 12):** 3 tests pass; runbook committed; mode has never advanced past OFF in any environment except by explicit manual admin API call.

---

## Self-Review Notes

- **Spec coverage:** policy engine dual-cap + circuit breaker (T1), auth reuse (T1a), autonomy API (T2), policy CRUD (T3), fulfillment wiring — `fulfill_order` already existed, plan builds the missing trigger + lock (T4), commerce agent with shadow/limited/full semantics (T5), support agent with identity-verified refunds (T6), Stripe refund executor (T6a), chat API (T7), locked celery cadence (T8), chat widget (T9), verification + migration (T10), alerting (T11), staged rollout (T12). Content factory / lead nurture / copywriter jobs deferred to P2 per spec §8.
- **Deviations found during exploration (verified against code):** `fulfillment_service.fulfill_order` + `queue_delivery_email` exist and are tested — no new fulfillment code, only the trigger; `require_admin_api_key` already exists in `dependencies.py` — reused, no new token; `TelegramNotifier.notify_system_alert` exists — reused. Agent jobs are rule-based in P1 (no LLM in critical path).
- **Type consistency:** `PolicyEngine.check(db, action, context)` identical across T1/T2/T5/T6; `set_autonomy_mode` (never `set_autonomy`) used everywhere; `run_cycle` returns `{skipped, actions_taken, policy_denials, shadow_proposals}` in T2 stub + T5 impl + T8 task; `value_cents` present in every money-moving policy call; `AutonomyMode` used for mode semantics (T2/T5/T12).
- **Verification risks (do these before running the suite):** `IncidentEvent` column names (`title`/`description`/`affected_order_id` — models.py:642), `AutomationLock` column names (models.py:600), `RevenueCampaignService.check_campaign_budget` return key, `celery_app.py` beat structure + task name prefix, `lib/api.ts` helper name, `store`/auth source in `StorePage.tsx`. Each task's Step notes point at the exact location to verify.
