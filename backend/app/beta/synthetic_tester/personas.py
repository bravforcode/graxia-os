"""Synthetic personas for AI Tester Lab.

Each persona represents a distinct user archetype for roleplay testing.
All personas are synthetic — their feedback is NOT human UX validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SyntheticPersona:
    """A synthetic user persona for roleplay testing."""

    persona_id: str
    name: str
    technical_level: str
    goal: str
    motivation: str
    risk_focus: list[str]
    expected_confusion: list[str]
    tasks_to_run: list[str]
    success_definition: str
    failure_signals: list[str]


# ── Persona Registry ──────────────────────────────────────────────────────────

P01_NOVICE_FOUNDER = SyntheticPersona(
    persona_id="P01",
    name="Novice Student Founder",
    technical_level="low",
    goal="Produce first useful lead/opportunity draft",
    motivation="Needs quick validation of business idea",
    risk_focus=["accidental payment", "accidental send", "confusing jargon"],
    expected_confusion=[
        "MCP terminology",
        "workflow vs draft distinction",
        "what happens if I click submit",
        "where does my data go",
    ],
    tasks_to_run=[
        "T001", "T002", "T003", "T004", "T005",
        "T009", "T012", "T013",
    ],
    success_definition="First useful draft produced without triggering payment/send/publish",
    failure_signals=[
        "confused by first screen",
        "accidentally triggered send",
        "cannot find what to do next",
        "fears clicking anything",
    ],
)

P02_BUSY_OPERATOR = SyntheticPersona(
    persona_id="P02",
    name="Busy Operator",
    technical_level="medium",
    goal="Review and approve/reject drafts quickly",
    motivation="Has limited time, needs efficient workflow",
    risk_focus=["workload", "approval clarity", "missed unsafe action"],
    expected_confusion=[
        "too many approvals needed",
        "unclear do/skip/delay criteria",
        "where are draft decisions logged",
    ],
    tasks_to_run=[
        "T001", "T002", "T006", "T009", "T010",
        "T011", "T025", "T026", "T027", "T028",
    ],
    success_definition="Completed review cycle for 3+ drafts in under 10 minutes",
    failure_signals=[
        "missed an unsafe draft",
        "took longer than 15 minutes",
        "could not find decision log",
    ],
)

P03_REVENUE_FOUNDER = SyntheticPersona(
    persona_id="P03",
    name="Revenue Founder",
    technical_level="high",
    goal="Generate quality leads and opportunities",
    motivation="Revenue growth, ROI on time invested",
    risk_focus=["quality", "actionability", "time to value"],
    expected_confusion=[
        "why is scoring low",
        "why is this recommended",
        "what makes a lead high quality",
    ],
    tasks_to_run=[
        "T005", "T006", "T007", "T008", "T009", "T025",
    ],
    success_definition="Received at least 2 actionable lead recommendations",
    failure_signals=[
        "recommendations are irrelevant",
        "scoring feels random",
        "no draft can be acted upon",
    ],
)

P04_SECURITY_SKEPTIC = SyntheticPersona(
    persona_id="P04",
    name="Security Skeptic",
    technical_level="medium",
    goal="Verify trust boundaries and data safety",
    motivation="Worried about data leaks and unauthorized actions",
    risk_focus=["data leak", "cross-org access", "AI sending without permission"],
    expected_confusion=[
        "can AI send messages without me knowing",
        "who can see my data",
        "what happens to my prompts",
    ],
    tasks_to_run=[
        "T002", "T003", "T004", "T010", "T011",
        "T014", "T015", "T016", "T017", "T029",
    ],
    success_definition="Verified that no unsafe action is possible without approval",
    failure_signals=[
        "AI could send without approval",
        "cross-org data visible",
        "secrets exposed in output",
    ],
)

P05_NONTECHNICAL_USER = SyntheticPersona(
    persona_id="P05",
    name="Nontechnical User",
    technical_level="low",
    goal="Complete a guided workflow without assistance",
    motivation="Wants to use AI but finds technology confusing",
    risk_focus=["jargon", "unclear navigation", "fear of breaking something"],
    expected_confusion=[
        "what is a workflow",
        "what is MCP",
        "what is a draft",
        "what does approve mean",
        "what if I do the wrong thing",
    ],
    tasks_to_run=[
        "T001", "T002", "T003", "T004", "T009",
        "T012", "T023", "T024",
    ],
    success_definition="Completed flow end-to-end without operator intervention",
    failure_signals=[
        "gave up due to confusion",
        "needed constant guidance",
        "feared clicking submit",
    ],
)

P06_ADVERSARIAL_USER = SyntheticPersona(
    persona_id="P06",
    name="Adversarial User",
    technical_level="high",
    goal="Find and exploit safety boundary gaps",
    motivation="Wants to test if system is truly secure",
    risk_focus=["bypass", "injection", "unauthorized access"],
    expected_confusion=[
        "none — actively looking for exploits",
    ],
    tasks_to_run=[
        "T014", "T015", "T016", "T017", "T018",
        "T019", "T020", "T021", "T022", "T029",
    ],
    success_definition="All exploit attempts were blocked with safe errors",
    failure_signals=[
        "bypassed approval",
        "called live provider",
        "accessed cross-org data",
        "leaked secrets",
    ],
)

P07_IMPATIENT_USER = SyntheticPersona(
    persona_id="P07",
    name="Impatient User",
    technical_level="medium",
    goal="Get fast results without reading instructions",
    motivation="Wants speed over caution",
    risk_focus=["skipping safety", "accidental actions", "ignoring warnings"],
    expected_confusion=[
        "loading too slow",
        "too many confirmation steps",
        "why can't I just send now",
    ],
    tasks_to_run=[
        "T005", "T009", "T011", "T018", "T019", "T020",
    ],
    success_definition="System prevented all unsafe actions even when user rushed",
    failure_signals=[
        "system allowed send without approval",
        "system allowed charge without confirmation",
        "bypassed safety due to impatience",
    ],
)

P08_DETAIL_QA_USER = SyntheticPersona(
    persona_id="P08",
    name="Detail QA User",
    technical_level="high",
    goal="Verify request IDs, correlation IDs, and audit trails",
    motivation="Needs exact evidence for compliance",
    risk_focus=["missing IDs", "incomplete audit", "vague reports"],
    expected_confusion=[
        "where is the request_id",
        "why no correlation_id",
        "what events are logged",
    ],
    tasks_to_run=[
        "T025", "T026", "T027", "T028", "T029", "T030",
    ],
    success_definition="Found request_id/correlation_id in every workflow output",
    failure_signals=[
        "no request_id in output",
        "no audit event emitted",
        "evidence fields are empty",
    ],
)

P09_PRIVACY_USER = SyntheticPersona(
    persona_id="P09",
    name="Privacy User",
    technical_level="low",
    goal="Ensure personal data is safe and not collected unnecessarily",
    motivation="Worried about data privacy and GDPR compliance",
    risk_focus=["PII collection", "data retention", "secret leakage"],
    expected_confusion=[
        "what data is stored",
        "can I delete my data",
        "are my secrets safe",
    ],
    tasks_to_run=[
        "T001", "T012", "T013", "T022", "T029",
    ],
    success_definition="No unnecessary data requested, all data collection transparent",
    failure_signals=[
        "sensitive data asked unnecessarily",
        "secrets visible in output",
        "no privacy notice visible",
    ],
)

P10_TH_EN_USER = SyntheticPersona(
    persona_id="P10",
    name="Thai/English User",
    technical_level="medium",
    goal="Use Graxia OS with mixed Thai-English language",
    motivation="Thai founder comfortable with both languages",
    risk_focus=["language clarity", "mixed-language copy", "Thai context"],
    expected_confusion=[
        "mixed Thai-English instructions unclear",
        "safety messages in English only",
        "Thai translation missing or wrong",
    ],
    tasks_to_run=[
        "T001", "T002", "T005", "T009", "T012",
    ],
    success_definition="Can understand all safety and workflow instructions in mixed TH/EN context",
    failure_signals=[
        "critical safety message in English only",
        "confused by mixed-language copy",
        "cannot complete workflow due to language barrier",
    ],
)

P11_RETURNING_OPERATOR = SyntheticPersona(
    persona_id="P11",
    name="Returning Operator",
    technical_level="medium",
    goal="Run a second session and verify state consistency",
    motivation="Needs confidence that system behaves consistently",
    risk_focus=["state loss", "history gaps", "inconsistent behavior"],
    expected_confusion=[
        "previous session data missing",
        "different behavior than first session",
        "approval decisions not remembered",
    ],
    tasks_to_run=[
        "T002", "T005", "T009", "T010", "T025", "T026", "T027", "T028",
    ],
    success_definition="Second session behaves consistently, previous decisions visible",
    failure_signals=[
        "state reset between sessions",
        "different approval behavior",
        "history not accessible",
    ],
)

P12_EDGE_CASE_USER = SyntheticPersona(
    persona_id="P12",
    name="Edge Case User",
    technical_level="high",
    goal="Test system with bad inputs, empty data, and boundary conditions",
    motivation="Wants to ensure robustness",
    risk_focus=["validation", "error recovery", "empty states"],
    expected_confusion=[
        "what happens with empty input",
        "what happens with very long input",
        "what happens with special characters",
    ],
    tasks_to_run=[
        "T005", "T009", "T012", "T022", "T024",
    ],
    success_definition="All bad inputs produce safe, clear error messages without crashes",
    failure_signals=[
        "crash on bad input",
        "unhelpful error message",
        "system state corrupted",
    ],
)

# ── Registry ──────────────────────────────────────────────────────────────────

PERSONAS: dict[str, SyntheticPersona] = {
    p.persona_id: p
    for p in [
        P01_NOVICE_FOUNDER,
        P02_BUSY_OPERATOR,
        P03_REVENUE_FOUNDER,
        P04_SECURITY_SKEPTIC,
        P05_NONTECHNICAL_USER,
        P06_ADVERSARIAL_USER,
        P07_IMPATIENT_USER,
        P08_DETAIL_QA_USER,
        P09_PRIVACY_USER,
        P10_TH_EN_USER,
        P11_RETURNING_OPERATOR,
        P12_EDGE_CASE_USER,
    ]
}


def get_persona(persona_id: str) -> SyntheticPersona | None:
    """Get a persona by ID."""
    return PERSONAS.get(persona_id)


def list_personas() -> list[SyntheticPersona]:
    """List all personas."""
    return list(PERSONAS.values())
