from __future__ import annotations

from app.context_engine.escalation import EscalationStage, decide_auto_escalation


def test_auto_escalation_after_test_failure() -> None:
    decision = decide_auto_escalation(
        trigger="test_failure",
        previous_stage=EscalationStage.MAP_SIGNATURES,
        attempt=1,
    )
    assert decision.next_stage == EscalationStage.LINE_RANGES
    assert decision.include_related_tests is True


def test_auto_escalation_disables_compression_for_security() -> None:
    decision = decide_auto_escalation(
        trigger="type_error",
        previous_stage=EscalationStage.FULL_FILE,
        attempt=2,
        security_sensitive=True,
    )
    assert decision.next_stage == EscalationStage.DISABLE_COMPRESSION
    assert decision.disable_compression is True
