"""Confidence scoring for AI Tester Lab.

Calculates confidence scores across multiple dimensions with caps based on
evidence quality and runtime state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .evidence import SyntheticEvidence
from .honesty_gate import Verdict, run_honesty_gate


@dataclass
class ConfidenceScores:
    """Aggregated confidence scores with caps."""

    synthetic_beta_confidence: int = 0
    human_ux_confidence: int = 0
    ui_confidence: int = 0
    api_confidence: int = 0
    workflow_confidence: int = 0
    mcp_confidence: int = 0
    security_confidence: int = 0
    operator_confidence: int = 0
    accessibility_confidence: int = 0
    evidence_quality: int = 0

    # Applied caps
    caps_applied: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def apply_cap(self, score_name: str, max_value: int, reason: str) -> None:
        """Apply a cap to a score."""
        current = getattr(self, score_name, 0)
        if current > max_value:
            setattr(self, score_name, max_value)
            self.caps_applied.append(f"{score_name} capped at {max_value}: {reason}")

    def summary(self) -> str:
        """Return a summary of all scores."""
        lines = ["=== Confidence Scores ==="]
        for field_name in [
            "synthetic_beta_confidence",
            "human_ux_confidence",
            "ui_confidence",
            "api_confidence",
            "workflow_confidence",
            "mcp_confidence",
            "security_confidence",
            "operator_confidence",
            "accessibility_confidence",
            "evidence_quality",
        ]:
            value = getattr(self, field_name)
            lines.append(f"  {field_name}: {value}")
        for cap in self.caps_applied:
            lines.append(f"  ⚠ {cap}")
        for lim in self.limitations:
            lines.append(f"  ⚠ {lim}")
        return "\n".join(lines)


def calculate_confidence(evidence: SyntheticEvidence) -> ConfidenceScores:
    """Calculate confidence scores from evidence, applying honesty gate caps."""

    # First, run the honesty gate
    gate_result = run_honesty_gate(evidence)
    scores = ConfidenceScores()

    # Base confidence from evidence result
    if evidence.result == "PASS":
        base = 80
    elif evidence.result == "PARTIAL":
        base = 50
    elif evidence.result == "FAIL":
        base = 20
    else:
        base = 0

    # Synthetic beta confidence
    scores.synthetic_beta_confidence = min(base + len(evidence.workflow_runs) * 5, 100)

    # Human UX confidence — capped at 40 without real human
    scores.human_ux_confidence = 0  # No real human = 0

    # UI confidence
    if evidence.browser_used:
        scores.ui_confidence = min(base + len(evidence.ui_actions) * 5, 100)
    else:
        scores.ui_confidence = 0
        scores.limitations.append("UI confidence: 0 (no browser used)")

    # API confidence
    if evidence.api_calls:
        success_rate = sum(1 for c in evidence.api_calls if c.status_code < 400) / max(len(evidence.api_calls), 1)
        scores.api_confidence = min(int(base * success_rate), 100)
    else:
        scores.api_confidence = 0
        scores.limitations.append("API confidence: 0 (no API calls made)")

    # Workflow confidence
    if evidence.workflow_runs:
        success_rate = sum(1 for w in evidence.workflow_runs if w.result == "PASS") / max(len(evidence.workflow_runs), 1)
        scores.workflow_confidence = min(int(80 * success_rate) + 10, 100)
    else:
        scores.workflow_confidence = 0
        scores.limitations.append("Workflow confidence: 0 (no workflow runs)")

    # MCP confidence
    if evidence.mcp_calls:
        success_rate = sum(1 for m in evidence.mcp_calls if m.result == "PASS") / max(len(evidence.mcp_calls), 1)
        scores.mcp_confidence = min(int(80 * success_rate) + 10, 100)
    else:
        scores.mcp_confidence = 0
        scores.limitations.append("MCP confidence: 0 (no MCP calls)")

    # Security confidence
    security_checks = sum(1 for c in evidence.safe_errors if c.error_type in ("cross_org_blocked", "permission_denied", "kill_switch_blocked"))
    scores.security_confidence = min(base + security_checks * 10, 100)

    # Operator confidence
    operator_tasks = sum(1 for w in evidence.workflow_runs if w.mode == "approval")
    scores.operator_confidence = min(base + operator_tasks * 10, 100)

    # Accessibility confidence
    scores.accessibility_confidence = 0  # No UI to test
    scores.limitations.append("Accessibility confidence: 0 (no browser UI available)")

    # Evidence quality
    id_count = len(evidence.request_ids) + len(evidence.correlation_ids)
    scores.evidence_quality = min(id_count * 10 + 10, 100)

    # ── Apply Honesty Gate Caps ──

    for check in gate_result.checks:
        if check.rule_id == "H001" and check.verdict is Verdict.FAIL:
            scores.ui_confidence = 0
            scores.caps_applied.append("UI confidence zeroed: H001 (no browser)")
        elif check.rule_id == "H002" and check.verdict is Verdict.FAIL:
            scores.api_confidence = 0
            scores.caps_applied.append("API confidence zeroed: H002 (no API calls)")
        elif check.rule_id == "H006" and check.verdict is Verdict.WARN:
            scores.apply_cap("evidence_quality", 60, "H006 (missing correlation IDs)")
        elif check.rule_id == "H011" and check.verdict is Verdict.WARN:
            scores.apply_cap("ui_confidence", 50, "H011 (browser E2E deferred)")
        elif check.rule_id == "H012" and check.verdict is Verdict.WARN:
            scores.apply_cap("human_ux_confidence", 40, "H012 (no real human)")

    # Hard fail check — if any honesty gate FAIL, overall confidence is zeroed
    if gate_result.hard_fail:
        for score_field in [
            "synthetic_beta_confidence",
            "human_ux_confidence",
            "ui_confidence",
            "api_confidence",
            "workflow_confidence",
            "mcp_confidence",
            "security_confidence",
            "operator_confidence",
            "accessibility_confidence",
            "evidence_quality",
        ]:
            setattr(scores, score_field, 0)
        scores.limitations.append("ALL SCORES ZEROED: honesty gate hard fail")
        scores.caps_applied.append("Honesty gate HARD FAIL — all confidence scores zeroed")

    return scores
