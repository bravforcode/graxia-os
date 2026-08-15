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
from ...models import AuditLog, AutonomyState, IncidentEvent, PolicyRule, StrategyLog
from graxia.services.telegram_notifier import UnifiedTelegramNotifier

logger = structlog.get_logger()

SHADOW_MIN_DAYS = 7
LIMITED_MIN_DAYS = 7
SHADOW_MIN_DECISIONS = 10
MAX_DENIALS_PER_DAY = 2


async def days_in_mode(db: AsyncSession, mode: AutonomyMode) -> int:
    """Days since the autonomy mode was last set. Reads the singleton row.
    Module-level so tests can monkeypatch it (must be an async function)."""
    from ...constants import AUTONOMY_STATE_ID
    state = await db.scalar(select(AutonomyState).where(AutonomyState.id == AUTONOMY_STATE_ID))
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
            select(func.count(IncidentEvent.id)).where(
                IncidentEvent.severity == IncidentSeverity.MEDIUM,
                IncidentEvent.created_at >= datetime.utcnow() - timedelta(days=1),
            )
        )
        breaker_trips = await db.scalar(
            select(func.count(IncidentEvent.id)).where(
                IncidentEvent.severity == IncidentSeverity.HIGH,
                IncidentEvent.title.like("Circuit breaker%"),
            )
        )
        days = await days_in_mode(db, mode)

        if mode == AutonomyMode.OFF:
            gates["rules_seeded"] = bool(rule_count and rule_count >= 6)
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
            gates["breaker_never_tripped"] = (breaker_trips or 0) == 0
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
            await UnifiedTelegramNotifier().notify_system_alert(
                severity="info",
                msg=f"Autonomy stage={readiness['stage']} ready_for_next={readiness['ready_for_next']}",
            )
        except Exception:
            logger.exception("rollout_notify_failed")
        return readiness


async def rollout_gate_checker():
    async with get_db_session() as db:
        return await RolloutGateChecker.run_daily(db)
