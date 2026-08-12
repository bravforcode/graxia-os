"""Honesty Gate — Automated rules to prevent overclaiming in AI Tester Lab.

Each rule checks evidence and returns a verdict (PASS, FAIL, WARN) with
an explanation. The gate prevents the AI from claiming:
- UI tested without browser evidence
- API tested without runtime calls
- Human feedback without human participants
- Production readiness when false
- Etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from .evidence import SyntheticEvidence


class Verdict(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class HonestyCheck:
    """Result of a single honesty gate check."""

    rule_id: str
    description: str
    verdict: Verdict
    message: str


@dataclass
class HonestyGateResult:
    """Aggregated honesty gate result."""

    checks: list[HonestyCheck] = field(default_factory=list)
    hard_fail: bool = False

    def add(self, rule_id: str, description: str, verdict: Verdict, message: str) -> None:
        self.checks.append(HonestyCheck(rule_id=rule_id, description=description, verdict=verdict, message=message))
        if verdict == Verdict.FAIL:
            self.hard_fail = True

    def all_pass(self) -> bool:
        return not self.hard_fail and all(c.verdict != Verdict.FAIL for c in self.checks)

    def summary(self) -> str:
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c.verdict == Verdict.PASS)
        warned = sum(1 for c in self.checks if c.verdict == Verdict.WARN)
        failed = sum(1 for c in self.checks if c.verdict == Verdict.FAIL)
        return f"HonestyGate: {passed}/{total} pass, {warned} warn, {failed} fail (hard_fail={self.hard_fail})"


# ── Rule Definitions ─────────────────────────────────────────────────────────

# Downgrade table for unsupported claims
CLAIM_DOWNGRADES: dict[str, str] = {
    "UX validated": "UX hypothesis only",
    "human feedback": "AI persona feedback",
    "UI tested": "UI not tested / browser deferred",
    "API tested": "API not runtime-tested",
    "workflow executed": "workflow verified by tests only",
    "production-ready": "production remains false",
    "beta validated": "synthetic beta validated only",
}


def check_h001_browser_claim(evidence: SyntheticEvidence) -> HonestyCheck:
    """H001: If browser_used=false, UI_TESTED claim is forbidden."""
    if not evidence.browser_used:
        return HonestyCheck(
            rule_id="H001",
            description="browser_used=false → UI_TESTED claim forbidden",
            verdict=Verdict.PASS if evidence.test_type != "BROWSER_E2E" else Verdict.FAIL,
            message="Browser was not used; UI tested claims would be downgraded to 'UX hypothesis only'",
        )
    return HonestyCheck(rule_id="H001", description="browser_used=true", verdict=Verdict.PASS, message="Browser was used, UI claims are valid")


def check_h002_api_claim(evidence: SyntheticEvidence) -> HonestyCheck:
    """H002: If api_calls empty, API_TESTED claim is forbidden."""
    if not evidence.api_calls:
        return HonestyCheck(
            rule_id="H002",
            description="api_calls empty → API_TESTED claim forbidden",
            verdict=Verdict.PASS if evidence.test_type != "API_RUNTIME" else Verdict.FAIL,
            message="No API calls were made; API runtime tested claims are not supported",
        )
    return HonestyCheck(rule_id="H002", description="api_calls present", verdict=Verdict.PASS, message=f"{len(evidence.api_calls)} API calls recorded")


def check_h003_workflow_claim(evidence: SyntheticEvidence) -> HonestyCheck:
    """H003: If workflow_runs empty, WORKFLOW_EXECUTED claim is forbidden."""
    if not evidence.workflow_runs:
        return HonestyCheck(
            rule_id="H003",
            description="workflow_runs empty → WORKFLOW_EXECUTED claim forbidden",
            verdict=Verdict.WARN,
            message="No workflow runs recorded; execution would be downgraded to 'verified by tests only'",
        )
    return HonestyCheck(rule_id="H003", description="workflow_runs present", verdict=Verdict.PASS, message=f"{len(evidence.workflow_runs)} workflow runs recorded")


def check_h004_synthetic_claim(evidence: SyntheticEvidence) -> HonestyCheck:
    """H004: If role is synthetic, HUMAN_FEEDBACK claim is forbidden."""
    if evidence.test_type in ("SYNTHETIC_ROLEPLAY", "STATIC_REVIEW"):
        return HonestyCheck(
            rule_id="H004",
            description="synthetic role → HUMAN_FEEDBACK claim forbidden",
            verdict=Verdict.PASS,
            message="Evidence is labeled synthetic; human feedback claims would be downgraded to 'AI persona feedback'",
        )
    return HonestyCheck(rule_id="H004", description="not synthetic role", verdict=Verdict.PASS, message="Role is not exclusively synthetic")


def check_h005_runtime_claim(evidence: SyntheticEvidence) -> HonestyCheck:
    """H005: If backend_running=false, RUNTIME_TESTED claim is forbidden."""
    if not evidence.backend_running:
        return HonestyCheck(
            rule_id="H005",
            description="backend_running=false → RUNTIME_TESTED claim forbidden",
            verdict=Verdict.PASS if evidence.test_type != "API_RUNTIME" else Verdict.FAIL,
            message="Backend was not running; runtime tested claims are not supported",
        )
    return HonestyCheck(rule_id="H005", description="backend_running=true", verdict=Verdict.PASS, message="Backend was running, runtime claims are valid")


def check_h006_correlation_ids(evidence: SyntheticEvidence) -> HonestyCheck:
    """H006: If request_ids/correlation_ids missing, evidence quality capped."""
    has_ids = bool(evidence.request_ids) and bool(evidence.correlation_ids)
    if not has_ids:
        return HonestyCheck(
            rule_id="H006",
            description="request_ids/correlation_ids missing → evidence quality capped",
            verdict=Verdict.WARN,
            message="No request or correlation IDs captured; evidence quality is capped at 60",
        )
    return HonestyCheck(rule_id="H006", description="correlation IDs present", verdict=Verdict.PASS, message=f"{len(evidence.request_ids)} request_ids, {len(evidence.correlation_ids)} correlation_ids")


def check_h007_production_ready(evidence: SyntheticEvidence) -> HonestyCheck:
    """H007: If production_ready=true, hard fail."""
    if evidence.production_ready:
        return HonestyCheck(
            rule_id="H007",
            description="production_ready=true → HARD FAIL",
            verdict=Verdict.FAIL,
            message="Production readiness is enabled! This must never happen during testing.",
        )
    return HonestyCheck(rule_id="H007", description="production_ready=false", verdict=Verdict.PASS, message="Production readiness correctly disabled")


def check_h008_live_providers(evidence: SyntheticEvidence) -> HonestyCheck:
    """H008: If any live provider flag true, hard fail."""
    for flag, value in evidence.live_provider_flags.items():
        if value:
            return HonestyCheck(
                rule_id="H008",
                description=f"live provider flag {flag}=true → HARD FAIL",
                verdict=Verdict.FAIL,
                message=f"Live provider {flag} is enabled! This must never happen during testing.",
            )
    return HonestyCheck(rule_id="H008", description="live providers false", verdict=Verdict.PASS, message="All live provider flags correctly disabled")


def check_h009_approval_bypass(evidence: SyntheticEvidence) -> HonestyCheck:
    """H009: If approval bypass observed, hard fail."""
    for wf in evidence.workflow_runs:
        if "bypass" in wf.result.lower() or "auto_send" in wf.result.lower():
            return HonestyCheck(
                rule_id="H009",
                description="approval bypass observed → HARD FAIL",
                verdict=Verdict.FAIL,
                message=f"Workflow {wf.workflow_name} had result '{wf.result}' indicating possible bypass",
            )
    return HonestyCheck(rule_id="H009", description="no approval bypass", verdict=Verdict.PASS, message="No approval bypass observed")


def check_h010_raw_token_leak(evidence: SyntheticEvidence) -> HonestyCheck:
    """H010: If raw token/secret in evidence, hard fail."""
    # Check output summary for token-like patterns
    sensitive_patterns = ["sk-", "eyJ", "ghp_", "gho_", "xoxb-", "xoxp-"]
    if any(p in evidence.output_summary.lower() for p in sensitive_patterns):
        return HonestyCheck(
            rule_id="H010",
            description="raw token/secret pattern in evidence → HARD FAIL",
            verdict=Verdict.FAIL,
            message="Evidence output contains patterns that look like raw credentials",
        )
    return HonestyCheck(rule_id="H010", description="no raw token leak", verdict=Verdict.PASS, message="No raw credentials detected in evidence output")


def check_h011_browser_e2e_deferred(evidence: SyntheticEvidence) -> HonestyCheck:
    """H011: If browser E2E deferred, UI confidence capped."""
    if not evidence.browser_used:
        return HonestyCheck(
            rule_id="H011",
            description="browser_e2e deferred → UI confidence capped at 50",
            verdict=Verdict.WARN,
            message="Browser E2E was not executed; UI confidence is capped at 50. Do not claim UI tested.",
        )
    return HonestyCheck(rule_id="H011", description="browser E2E executed", verdict=Verdict.PASS, message="Browser E2E was executed")


def check_h012_no_real_human(evidence: SyntheticEvidence) -> HonestyCheck:
    """H012: If no real human, human UX confidence capped."""
    if evidence.test_type in ("SYNTHETIC_ROLEPLAY", "STATIC_REVIEW", "TEST_HARNESS", "ADVERSARIAL_SECURITY"):
        return HonestyCheck(
            rule_id="H012",
            description="no real human → human UX confidence capped at 40",
            verdict=Verdict.WARN,
            message="No real human participant; human UX confidence is capped at 40. Do not claim human feedback.",
        )
    return HonestyCheck(rule_id="H012", description="real human involved", verdict=Verdict.PASS, message="Real human feedback may be present")


# ── Runner ────────────────────────────────────────────────────────────────────


def run_honesty_gate(evidence: SyntheticEvidence) -> HonestyGateResult:
    """Run all honesty gate rules against evidence."""
    result = HonestyGateResult()

    def _add(check: HonestyCheck) -> None:
        result.add(check.rule_id, check.description, check.verdict, check.message)

    _add(check_h001_browser_claim(evidence))
    _add(check_h002_api_claim(evidence))
    _add(check_h003_workflow_claim(evidence))
    _add(check_h004_synthetic_claim(evidence))
    _add(check_h005_runtime_claim(evidence))
    _add(check_h006_correlation_ids(evidence))
    _add(check_h007_production_ready(evidence))
    _add(check_h008_live_providers(evidence))
    _add(check_h009_approval_bypass(evidence))
    _add(check_h010_raw_token_leak(evidence))
    _add(check_h011_browser_e2e_deferred(evidence))
    _add(check_h012_no_real_human(evidence))

    return result
