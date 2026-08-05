"""
gates.py — HARD human-review gates (Spec Part 3, steps 7 & 10).

These are real control-flow blocks, not comments. The loop MUST check the
returned GateState and STOP if it is not CLEARED. There is no code path that
auto-clears a gate.

  Step 7  — after a candidate survives the exploratory gates (DK + label-shuffle
            + min-trades), opening the sacred holdout REQUIRES human sign-off.
  Step 10 — paper trading (>=60d) and live deployment REQUIRE human sign-off.
            The loop NEVER deploys to live capital.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GateState(Enum):
    CLEARED = "CLEARED"
    REQUIRES_HUMAN = "REQUIRES_HUMAN"
    BLOCKED = "BLOCKED"


@dataclass
class HumanDecision:
    """An explicit human sign-off. `token` is the same-turn authorization.

    Per CONTRIBUTING.md line 108, canonical ledger edits require explicit
    same-turn user sign-off. A HumanDecision carrying a non-empty token is how
    that sign-off is represented in the loop.
    """

    approved: bool
    reviewer: str
    token: str
    note: str = ""


def _valid(decision: HumanDecision | None) -> bool:
    return decision is not None and decision.approved and bool(decision.token)


def human_gate_step7(candidate_id: str, decision: HumanDecision | None = None) -> GateState:
    """Gate before opening the sacred holdout (one-time use).

    Returns REQUIRES_HUMAN unless a valid human decision is supplied. The loop
    must not open the holdout when this returns anything but CLEARED.
    """
    if not _valid(decision):
        return GateState.REQUIRES_HUMAN
    return GateState.CLEARED


def human_gate_step10(
    target: str, decision: HumanDecision | None = None
) -> GateState:
    """Gate before paper trading / live deployment.

    `target` is "paper" or "live". Live is never reached by the loop without an
    explicit, separate human decision; the loop only ever proposes paper.
    """
    if target not in ("paper", "live"):
        return GateState.BLOCKED
    if not _valid(decision):
        return GateState.REQUIRES_HUMAN
    return GateState.CLEARED
