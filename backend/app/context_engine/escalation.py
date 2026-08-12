"""Escalation policy for context correctness failures."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EscalationStage(StrEnum):
    MAP_SIGNATURES = "map_signatures"
    LINE_RANGES = "line_ranges"
    FULL_FILE = "full_file"
    RELATED_FILES = "related_files"
    DISABLE_COMPRESSION = "disable_compression"


_ORDER = [
    EscalationStage.MAP_SIGNATURES,
    EscalationStage.LINE_RANGES,
    EscalationStage.FULL_FILE,
    EscalationStage.RELATED_FILES,
    EscalationStage.DISABLE_COMPRESSION,
]


@dataclass
class EscalationDecision:
    previous_stage: EscalationStage
    next_stage: EscalationStage
    trigger: str
    reason: str
    disable_compression: bool = False
    include_related_tests: bool = False


def decide_auto_escalation(
    *,
    trigger: str,
    previous_stage: EscalationStage = EscalationStage.MAP_SIGNATURES,
    attempt: int = 1,
    security_sensitive: bool = False,
) -> EscalationDecision:
    if security_sensitive:
        return EscalationDecision(
            previous_stage=previous_stage,
            next_stage=EscalationStage.DISABLE_COMPRESSION,
            trigger=trigger,
            reason="Security-sensitive task requires no aggressive compression.",
            disable_compression=True,
            include_related_tests=True,
        )

    idx = _ORDER.index(previous_stage)
    step = 1 if attempt <= 1 else 2
    next_idx = min(idx + step, len(_ORDER) - 1)
    next_stage = _ORDER[next_idx]
    return EscalationDecision(
        previous_stage=previous_stage,
        next_stage=next_stage,
        trigger=trigger,
        reason=f"Escalated after {trigger} (attempt {attempt}).",
        disable_compression=next_stage == EscalationStage.DISABLE_COMPRESSION,
        include_related_tests=trigger in {"test_failure", "import_error", "type_error", "migration_failure"},
    )
