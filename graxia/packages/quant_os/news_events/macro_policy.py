from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class MacroSourceRole(Enum):
    RESEARCH = "RESEARCH"  # FRED/ALFRED, COT, LBMA, news headlines
    CALENDAR_VALIDATION = "CALENDAR_VALIDATION"  # Official release pages
    LIVE_DIRECTIONAL = "LIVE_DIRECTIONAL"  # FORBIDDEN


@dataclass(frozen=True)
class MacroObservation:
    source_name: str
    source_role: MacroSourceRole
    observation_timestamp: datetime
    release_timestamp: datetime
    available_to_strategy_timestamp: datetime
    revision_id: str
    payload_hash: str
    value: float | None = None

    def is_revision_safe(self, as_of: datetime) -> bool:
        """Ensure observation was available before query time (no future leakage)."""
        return self.available_to_strategy_timestamp <= as_of


class MacroPolicyGuard:
    """Enforce macro data policy: research-only roles, no intraday entry drivers."""

    FORBIDDEN_ROLES = {MacroSourceRole.LIVE_DIRECTIONAL}

    def __init__(self):
        self._observations: list[MacroObservation] = []

    def add_observation(self, obs: MacroObservation) -> None:
        self._observations.append(obs)

    def check_observation(self, obs: MacroObservation) -> tuple[bool, str]:
        if obs.source_role in self.FORBIDDEN_ROLES:
            return False, f"FORBIDDEN_ROLE:{obs.source_role.value}"

        if obs.source_role == MacroSourceRole.RESEARCH and obs.value is not None:
            return True, "RESEARCH_CONTEXT_ONLY"

        if obs.source_role == MacroSourceRole.CALENDAR_VALIDATION:
            return True, "CALENDAR_VALIDATION"

        return True, "ALLOWED"

    def get_available_observations(
        self, as_of: datetime, source_role: MacroSourceRole | None = None
    ) -> list[MacroObservation]:
        """Return observations available as of timestamp, respecting revision safety."""
        results = []
        for obs in self._observations:
            if not obs.is_revision_safe(as_of):
                continue
            if source_role and obs.source_role != source_role:
                continue
            results.append(obs)
        return results

    def validate_no_revision_leakage(self, as_of: datetime) -> tuple[bool, list[str]]:
        """Verify no future-dated observations are accessible."""
        violations = []
        for obs in self._observations:
            if obs.available_to_strategy_timestamp > as_of:
                violations.append(f"REVISION_LEAKAGE:{obs.source_name}:{obs.revision_id}")
        return len(violations) == 0, violations


class LLMPolicyGuard:
    """Enforce LLM/news usage boundaries: explanation only, never directional."""

    ALLOWED_USES = {
        "cluster_duplicate_headlines",
        "summarize_incident_context",
        "classify_source_type",
        "create_human_readable_briefing",
        "propose_offline_research_hypothesis",
    }

    FORBIDDEN_USES = {
        "convert_headline_to_trade_direction",
        "set_confidence_threshold_for_trade",
        "modify_stop_loss",
        "change_risk_policy",
        "invoke_execution",
        "override_event_blackout",
    }

    def check_llm_action(self, action_type: str) -> tuple[bool, str]:
        if action_type in self.FORBIDDEN_USES:
            return False, f"FORBIDDEN_LLM_ACTION:{action_type}"
        if action_type in self.ALLOWED_USES:
            return True, "ALLOWED"
        return False, f"UNKNOWN_ACTION:{action_type}"
