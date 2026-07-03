"""Phase BE-P13 — Expansion readiness check."""
from dataclasses import dataclass


@dataclass
class ReadinessCheck:
    check_name: str
    description: str
    passed: bool = False
    detail: str = ""


class ExpansionReadiness:
    """Check readiness before expansion."""

    def check(self, context: dict) -> list[ReadinessCheck]:
        checks = []

        checks.append(ReadinessCheck(
            "current_tier_proven",
            "Current tier has sufficient evidence",
            context.get("current_tier_proven", False),
        ))

        checks.append(ReadinessCheck(
            "no_safety_incidents",
            "No unresolved safety incidents",
            context.get("safety_incidents", 0) == 0,
        ))

        checks.append(ReadinessCheck(
            "risk_limits_respected",
            "Risk limits not breached",
            context.get("risk_breaches", 0) == 0,
        ))

        checks.append(ReadinessCheck(
            "broker_identity_locked",
            "Broker identity verified",
            context.get("broker_identity_locked", False),
        ))

        checks.append(ReadinessCheck(
            "cost_model_stable",
            "Cost model within tolerance",
            context.get("cost_gap_pct", 100) <= 50,
        ))

        return checks

    def all_passed(self, context: dict) -> bool:
        return all(c.passed for c in self.check(context))
