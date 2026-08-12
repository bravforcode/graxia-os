"""In-memory beta cohort/allowlist registry.

Used for controlled external beta in Phase 19.
All data is runtime-only — no DB migration required.
Testers are manually added by the operator at startup or via API.

Supports:
- Beta tester registration with configurable limits
- Status tracking: invited | active | paused | removed
- Per-tester daily session/workflow/MCP caps
- Global kill switch integration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class BetaTesterStatus(str, Enum):
    INVITED = "invited"
    ACTIVE = "active"
    PAUSED = "paused"
    REMOVED = "removed"


class FeedbackSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FeedbackType(str, Enum):
    BUG = "bug"
    CONFUSION = "confusion"
    VALUE = "value"
    MISSING_FEATURE = "missing_feature"
    SAFETY_CONCERN = "safety_concern"


@dataclass
class BetaTesterLimits:
    """Per-tester daily usage limits."""
    max_sessions_per_day: int = 5
    max_workflows_per_day: int = 20
    max_mcp_calls_per_day: int = 100


@dataclass
class BetaTester:
    """A single beta tester in the controlled beta program."""
    tester_id: UUID = field(default_factory=uuid4)
    organization_id: UUID | None = None
    email_hash: str = ""  # SHA-256 hash of email, no raw email stored
    status: BetaTesterStatus = BetaTesterStatus.INVITED
    limits: BetaTesterLimits = field(default_factory=BetaTesterLimits)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def activate(self) -> None:
        self.status = BetaTesterStatus.ACTIVE
        self.updated_at = datetime.utcnow()

    def pause(self) -> None:
        self.status = BetaTesterStatus.PAUSED
        self.updated_at = datetime.utcnow()

    def remove(self) -> None:
        self.status = BetaTesterStatus.REMOVED
        self.updated_at = datetime.utcnow()


@dataclass
class BetaFeedback:
    """Feedback submitted by a beta tester."""
    feedback_id: UUID = field(default_factory=uuid4)
    tester_id: UUID | None = None
    organization_id: UUID | None = None
    feedback_type: FeedbackType = FeedbackType.BUG
    severity: FeedbackSeverity = FeedbackSeverity.LOW
    message: str = ""
    request_id: str = ""
    correlation_id: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


class BetaRegistry:
    """In-memory registry for beta testers and feedback.

    No secrets, no raw emails, no production data.
    """

    def __init__(self) -> None:
        self._testers: dict[str, BetaTester] = {}  # key: email_hash
        self._feedback: list[BetaFeedback] = []

    # ── Tester Management ──────────────────────────────────────────────

    def add_tester(
        self,
        email_hash: str,
        organization_id: UUID | None = None,
        limits: BetaTesterLimits | None = None,
    ) -> BetaTester:
        """Add a new beta tester (invited status by default)."""
        if email_hash in self._testers:
            raise ValueError(f"Tester with email_hash '{email_hash[:8]}...' already exists")
        tester = BetaTester(
            email_hash=email_hash,
            organization_id=organization_id,
            limits=limits or BetaTesterLimits(),
            status=BetaTesterStatus.INVITED,
        )
        self._testers[email_hash] = tester
        return tester

    def get_tester(self, email_hash: str) -> BetaTester | None:
        return self._testers.get(email_hash)

    def get_tester_by_id(self, tester_id: UUID) -> BetaTester | None:
        for tester in self._testers.values():
            if tester.tester_id == tester_id:
                return tester
        return None

    def is_active(self, email_hash: str) -> bool:
        tester = self._testers.get(email_hash)
        return tester is not None and tester.status == BetaTesterStatus.ACTIVE

    def is_invited(self, email_hash: str) -> bool:
        tester = self._testers.get(email_hash)
        return tester is not None and tester.status == BetaTesterStatus.INVITED

    def is_paused(self, email_hash: str) -> bool:
        tester = self._testers.get(email_hash)
        return tester is not None and tester.status == BetaTesterStatus.PAUSED

    def activate_tester(self, email_hash: str) -> BetaTester | None:
        tester = self._testers.get(email_hash)
        if tester:
            tester.activate()
        return tester

    def pause_tester(self, email_hash: str) -> BetaTester | None:
        tester = self._testers.get(email_hash)
        if tester:
            tester.pause()
        return tester

    def remove_tester(self, email_hash: str) -> bool:
        tester = self._testers.pop(email_hash, None)
        return tester is not None

    def list_active_testers(self) -> list[BetaTester]:
        return [t for t in self._testers.values() if t.status == BetaTesterStatus.ACTIVE]

    def list_all_testers(self) -> list[BetaTester]:
        return list(self._testers.values())

    def tester_count(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for tester in self._testers.values():
            counts[tester.status.value] = counts.get(tester.status.value, 0) + 1
        return counts

    # ── Limits & Usage ─────────────────────────────────────────────────

    def get_limits(self, email_hash: str) -> BetaTesterLimits | None:
        tester = self._testers.get(email_hash)
        return tester.limits if tester else None

    # ── Feedback ───────────────────────────────────────────────────────

    def submit_feedback(
        self,
        feedback_type: FeedbackType,
        severity: FeedbackSeverity,
        message: str,
        tester_id: UUID | None = None,
        organization_id: UUID | None = None,
        request_id: str = "",
        correlation_id: str = "",
    ) -> BetaFeedback:
        """Submit beta feedback. No secrets allowed in message."""
        feedback = BetaFeedback(
            tester_id=tester_id,
            organization_id=organization_id,
            feedback_type=feedback_type,
            severity=severity,
            message=message,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        self._feedback.append(feedback)
        return feedback

    def list_feedback(
        self,
        severity: FeedbackSeverity | None = None,
        feedback_type: FeedbackType | None = None,
        limit: int = 50,
    ) -> list[BetaFeedback]:
        results = list(self._feedback)
        if severity:
            results = [f for f in results if f.severity == severity]
        if feedback_type:
            results = [f for f in results if f.feedback_type == feedback_type]
        return sorted(results, key=lambda f: f.created_at, reverse=True)[:limit]

    def feedback_count_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for fb in self._feedback:
            counts[fb.severity.value] = counts.get(fb.severity.value, 0) + 1
        return counts

    def feedback_count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for fb in self._feedback:
            counts[fb.feedback_type.value] = counts.get(fb.feedback_type.value, 0) + 1
        return counts

    # ── Reset (for testing) ───────────────────────────────────────────

    def reset(self) -> None:
        self._testers.clear()
        self._feedback.clear()


# Global singleton (replaced in tests)
_beta_registry: BetaRegistry | None = None


def get_beta_registry() -> BetaRegistry:
    global _beta_registry
    if _beta_registry is None:
        _beta_registry = BetaRegistry()
    return _beta_registry


def reset_beta_registry() -> None:
    global _beta_registry
    _beta_registry = None
