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
from ..enums import ActionType, AutonomyMode, IncidentSeverity, RuleType, ValueType
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
        if rule.scope == "product_id" and context.get("product_id") != rule.scope_value:
            return False, None
        if rule.scope not in ("global", "product_id"):
            # Unknown scope is never applicable — an unrecognized scope must not
            # silently behave as global (latent fail-open for ALLOW rules).
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
