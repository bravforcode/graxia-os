from dataclasses import dataclass

@dataclass
class FailureRule:
    name: str
    description: str
    blocks_progression: bool = True

FAILURE_RULES = [
    FailureRule("STALE_DATA_ACCEPTED", "Stale data accepted into pipeline", True),
    FailureRule("EVENT_BLOCK_BYPASS", "Order intent while event blocked", True),
    FailureRule("MISSING_CONTRACT", "Missing contract snapshot accepted", True),
    FailureRule("INVALID_SL_ACCEPTED", "Invalid SL accepted", True),
    FailureRule("RISK_BREACH", "Risk budget breach", True),
    FailureRule("DUPLICATE_IDEMPOTENCY", "Duplicate idempotency key", True),
    FailureRule("INVALID_TRANSITION", "State machine invalid transition", True),
    FailureRule("UNCORRELATED_ALERT", "Uncorrelated critical alert", True),
    FailureRule("PIPELINE_EXCEPTION", "Unhandled exception in canonical pipeline", True),
]

class FailureRuleChecker:
    def __init__(self):
        self._violations: list[dict] = []

    def check(self, rule_name: str, context: dict = None) -> bool:
        rule = next((r for r in FAILURE_RULES if r.name == rule_name), None)
        if rule is None:
            return False

        if rule.blocks_progression:
            self._violations.append({
                "rule": rule_name,
                "description": rule.description,
                "context": context or {},
            })
            return True
        return False

    def has_violations(self) -> bool:
        return len(self._violations) > 0

    def get_violations(self) -> list[dict]:
        return list(self._violations)

    def clear(self) -> None:
        self._violations.clear()
