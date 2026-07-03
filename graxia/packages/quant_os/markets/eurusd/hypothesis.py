"""Phase BE-P7 — EURUSD hypothesis system."""
from dataclasses import dataclass, asdict
import hashlib
import json


@dataclass
class EURUSDHypothesis:
    """Hypothesis template per BE-P7 spec."""
    hypothesis_id: str = ""
    market: str = "EURUSD"
    primary_timeframe: str = "H1"
    higher_context_timeframe: str = "H4"
    rationale: str = ""
    entry_rule: list = None
    exit_rule: list = None
    invalidation_rule: list = None
    known_failure_regimes: list = None
    expected_trade_frequency: dict = None
    parameter_budget: int = 12
    feature_availability_policy: str = "point_in_time_only"
    final_holdout_status: str = "LOCKED"

    def __post_init__(self):
        if self.entry_rule is None:
            self.entry_rule = []
        if self.exit_rule is None:
            self.exit_rule = []
        if self.invalidation_rule is None:
            self.invalidation_rule = []
        if self.known_failure_regimes is None:
            self.known_failure_regimes = []
        if self.expected_trade_frequency is None:
            self.expected_trade_frequency = {}

    def validate(self) -> tuple[bool, list[str]]:
        issues = []
        if not self.hypothesis_id:
            issues.append("hypothesis_id required")
        if not self.rationale:
            issues.append("rationale required (economic/structure, not indicator)")
        if self.parameter_budget <= 0:
            issues.append("parameter_budget must be > 0")
        if self.final_holdout_status not in ("LOCKED", "UNLOCKED"):
            issues.append(f"invalid final_holdout_status: {self.final_holdout_status}")
        return len(issues) == 0, issues

    def compute_hash(self) -> str:
        d = self.to_dict()
        d.pop("hypothesis_id", None)
        return hashlib.sha256(
            json.dumps(d, sort_keys=True, default=str).encode()
        ).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EURUSDHypothesis":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class HypothesisTracker:
    """Track hypothesis lifecycle."""
    active_hypothesis: str = ""
    archived_hypotheses: list = None
    current_phase: str = "research"  # research, validation, shadow, demo

    def __post_init__(self):
        if self.archived_hypotheses is None:
            self.archived_hypotheses = []

    def activate(self, hypothesis_id: str) -> None:
        if self.active_hypothesis:
            self.archived_hypotheses.append(self.active_hypothesis)
        self.active_hypothesis = hypothesis_id

    def archive(self, hypothesis_id: str, reason: str) -> None:
        if hypothesis_id == self.active_hypothesis:
            self.active_hypothesis = ""
        self.archived_hypotheses.append(hypothesis_id)

    def get_active(self) -> str:
        return self.active_hypothesis
