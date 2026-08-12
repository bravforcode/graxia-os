"""Phase BE-P13 — Controlled expansion planner."""
from dataclasses import dataclass
from enum import Enum


class ExpansionTier(Enum):
    TIER_1 = "tier_1"  # More evidence for one symbol
    TIER_2 = "tier_2"  # One additional strategy
    TIER_3 = "tier_3"  # One additional symbol
    TIER_4 = "tier_4"  # Cross-symbol correlation
    TIER_5 = "tier_5"  # Portfolio risk budget
    TIER_6 = "tier_6"  # Optional second broker
    TIER_7 = "tier_7"  # Optional cTrader/FIX
    TIER_8 = "tier_8"  # Optional ML regime filter
    TIER_9 = "tier_9"  # Optional crypto project


TIER_DESCRIPTIONS = {
    ExpansionTier.TIER_1: "More evidence for one symbol/one strategy",
    ExpansionTier.TIER_2: "One additional strategy, isolated",
    ExpansionTier.TIER_3: "One additional symbol, isolated",
    ExpansionTier.TIER_4: "Cross-symbol correlation and gross exposure model",
    ExpansionTier.TIER_5: "Portfolio risk budget",
    ExpansionTier.TIER_6: "Optional second broker comparison venue",
    ExpansionTier.TIER_7: "Optional cTrader/FIX evaluation",
    ExpansionTier.TIER_8: "Optional ML regime filter research",
    ExpansionTier.TIER_9: "Optional crypto project in separate system",
}


FORBIDDEN_EXPANSIONS = [
    "raising_risk_on_win_streak",
    "adding_symbols_to_recover_drawdown",
    "adding_brokers_to_hide_poor_evidence",
    "adding_llm_to_override_rejects",
    "mixing_crypto_and_fx",
    "using_xauusd_strategy_on_eurusd",
]


@dataclass
class ExpansionRequest:
    target_tier: str
    justification: str
    requesting_strategy: str = ""


@dataclass
class ExpansionDecision:
    approved: bool
    target_tier: str
    violations: list = None
    notes: str = ""

    def __post_init__(self):
        if self.violations is None:
            self.violations = []


class ExpansionPlanner:
    """Controlled expansion planner."""

    def __init__(self, current_tier: str = "tier_1"):
        self._current_tier = current_tier
        self._decisions: list[ExpansionDecision] = []

    def evaluate(self, request: ExpansionRequest) -> ExpansionDecision:
        """Evaluate expansion request."""
        violations = []

        # Check forbidden patterns
        justification_lower = request.justification.lower()
        for forbidden in FORBIDDEN_EXPANSIONS:
            forbidden_words = forbidden.replace("_", " ")
            if forbidden_words in justification_lower:
                violations.append(f"forbidden: {forbidden}")

        # Check tier progression
        tier_order = list(ExpansionTier)
        current_idx = tier_order.index(ExpansionTier(self._current_tier))
        target_idx = tier_order.index(ExpansionTier(request.target_tier))

        if target_idx > current_idx + 1:
            violations.append(f"tier_skip: cannot jump from {self._current_tier} to {request.target_tier}")

        approved = len(violations) == 0

        decision = ExpansionDecision(
            approved=approved,
            target_tier=request.target_tier,
            violations=violations,
            notes=f"current={self._current_tier}, target={request.target_tier}",
        )
        self._decisions.append(decision)
        return decision

    def advance_tier(self) -> str:
        """Advance to next tier."""
        tier_order = list(ExpansionTier)
        current_idx = tier_order.index(ExpansionTier(self._current_tier))
        if current_idx < len(tier_order) - 1:
            self._current_tier = tier_order[current_idx + 1].value
        return self._current_tier

    def get_current_tier(self) -> str:
        return self._current_tier

    def get_decisions(self) -> list[ExpansionDecision]:
        return self._decisions.copy()
