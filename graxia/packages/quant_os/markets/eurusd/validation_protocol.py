"""Phase BE-P7 — EURUSD validation protocol."""
from dataclasses import dataclass


@dataclass
class ValidationCheck:
    check_name: str
    description: str
    required: bool = True


class EURUSDValidationProtocol:
    """EURUSD-specific validation checks."""

    def __init__(self):
        self._checks = [
            ValidationCheck("separate_dataset", "EURUSD uses own dataset, not XAUUSD"),
            ValidationCheck("separate_contract", "EURUSD uses own contract snapshot"),
            ValidationCheck("separate_session", "EURUSD uses own session model"),
            ValidationCheck("separate_events", "EURUSD uses own event mapping"),
            ValidationCheck("hypothesis_documented", "Hypothesis rationale is economic/structural"),
            ValidationCheck("parameter_budget_respected", "Parameters within budget"),
            ValidationCheck("no_xauusd_transfer", "No XAUUSD parameters without hypothesis"),
            ValidationCheck("final_holdout_locked", "Final holdout period is locked"),
        ]

    def get_checks(self) -> list[ValidationCheck]:
        return self._checks.copy()

    def validate(self, evidence: dict) -> tuple[bool, list[str]]:
        """Validate evidence against protocol."""
        issues = []
        for check in self._checks:
            if check.required and not evidence.get(check.check_name, False):
                issues.append(f"FAIL: {check.check_name} — {check.description}")
        return len(issues) == 0, issues
