"""Phase BE-P11 — Review report generator."""

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class ReviewReport:
    strategy_id: str = ""
    decision: str = ""
    blockers: list = None
    evidence_summary: dict = None
    recommendation: str = ""
    operator_notes: str = ""
    timestamp_utc: str = ""

    def __post_init__(self):
        if self.blockers is None:
            self.blockers = []
        if self.evidence_summary is None:
            self.evidence_summary = {}
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(UTC).isoformat()

    def to_markdown(self) -> str:
        lines = [
            "# Promotion Review Report",
            f"**Strategy:** {self.strategy_id}",
            f"**Decision:** {self.decision}",
            f"**Timestamp:** {self.timestamp_utc}",
            "",
            "## Blockers",
        ]
        if self.blockers:
            for b in self.blockers:
                lines.append(f"- {b}")
        else:
            lines.append("- None")

        lines.append("\n## Evidence Summary")
        for k, v in self.evidence_summary.items():
            lines.append(f"- **{k}:** {v}")

        if self.recommendation:
            lines.append(f"\n## Recommendation\n{self.recommendation}")

        if self.operator_notes:
            lines.append(f"\n## Operator Notes\n{self.operator_notes}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "decision": self.decision,
            "blockers": self.blockers,
            "evidence_summary": self.evidence_summary,
            "recommendation": self.recommendation,
            "operator_notes": self.operator_notes,
            "timestamp_utc": self.timestamp_utc,
        }


class ReviewReportGenerator:
    """Generate review reports."""

    def generate(
        self,
        strategy_id: str,
        decision: str,
        blockers: list,
        evidence_summary: dict,
        recommendation: str = "",
        operator_notes: str = "",
    ) -> ReviewReport:
        return ReviewReport(
            strategy_id=strategy_id,
            decision=decision,
            blockers=blockers,
            evidence_summary=evidence_summary,
            recommendation=recommendation,
            operator_notes=operator_notes,
        )
