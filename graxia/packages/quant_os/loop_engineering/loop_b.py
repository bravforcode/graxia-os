"""
loop_b.py — LOOP B: Operational Loop (Spec Part 1, 3).

Separate entry point from Loop A. Used ONLY for strategies that have already
passed sacred-holdout confirmation (none exist in this system yet). It MONITORS
live performance, DETECTS decay, and ALERTS a human. It NEVER retunes a parameter
and deploys, and it NEVER calls the live executor. If a human approves
re-validation, it routes back to Loop A (a full re-pre-registration) — not a
silent retune (Spec Part 1: "ถ้า human approve re-validation: กลับไป Loop A ใหม่ทั้งหมด").
"""

from __future__ import annotations

from dataclasses import dataclass

from .gates import HumanDecision


@dataclass
class PerformanceSample:
    strategy_id: str
    metric: str  # e.g. "sharpe", "drawdown_pct"
    value: float
    timestamp: str = ""


@dataclass
class OperationalAlert:
    strategy_id: str
    decay_detected: bool
    metric: str
    value: float
    threshold: float
    human_action_required: bool
    route_to: str  # "" | "LOOP_A_REVALIDATION"
    note: str = ""


def run_operational_loop(
    sample: PerformanceSample,
    decay_threshold: float,
    human_decision: HumanDecision | None = None,
    lower_is_worse: bool = True,
) -> OperationalAlert:
    """Monitor one performance sample. Alert on decay; never auto-act.

    `lower_is_worse=True` (default, e.g. Sharpe): decay when value < threshold.
    `lower_is_worse=False` (e.g. drawdown): decay when value > threshold.
    """
    if lower_is_worse:
        decay = sample.value < decay_threshold
    else:
        decay = sample.value > decay_threshold

    if not decay:
        return OperationalAlert(
            strategy_id=sample.strategy_id,
            decay_detected=False,
            metric=sample.metric,
            value=sample.value,
            threshold=decay_threshold,
            human_action_required=False,
            route_to="",
            note="No decay detected. Continue monitoring.",
        )

    # Decay detected -> ALERT human. Do NOT retune or deploy.
    if human_decision is not None and human_decision.approved and bool(human_decision.token):
        return OperationalAlert(
            strategy_id=sample.strategy_id,
            decay_detected=True,
            metric=sample.metric,
            value=sample.value,
            threshold=decay_threshold,
            human_action_required=True,
            route_to="LOOP_A_REVALIDATION",
            note="Human approved re-validation. Route back to Loop A (full re-pre-register). "
            "Loop B does NOT retune+deploy.",
        )

    return OperationalAlert(
        strategy_id=sample.strategy_id,
        decay_detected=True,
        metric=sample.metric,
        value=sample.value,
        threshold=decay_threshold,
        human_action_required=True,
        route_to="",
        note="Decay detected. Human alerted. Awaiting decision. Loop B does NOT retune or deploy.",
    )
