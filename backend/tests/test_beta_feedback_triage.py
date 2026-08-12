"""Test beta feedback and support triage flow."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.beta.registry import (
    BetaRegistry,
    BetaTesterLimits,
    FeedbackSeverity,
    FeedbackType,
    get_beta_registry,
    reset_beta_registry,
)


class TestBetaFeedbackFlow:
    """Beta feedback submission and triage tests."""

    def setup_method(self):
        reset_beta_registry()

    def test_feedback_submission_with_request_ids(self):
        """Feedback includes request_id and correlation_id for tracing."""
        registry = BetaRegistry()
        fb = registry.submit_feedback(
            feedback_type=FeedbackType.BUG,
            severity=FeedbackSeverity.HIGH,
            message="Dashboard not loading",
            request_id="req_test_123",
            correlation_id="corr_test_456",
        )
        assert fb.request_id == "req_test_123"
        assert fb.correlation_id == "corr_test_456"

    def test_feedback_submission_with_tester_id(self):
        """Feedback can include tester_id for attribution."""
        registry = BetaRegistry()
        tester = registry.add_tester(email_hash="tester1", organization_id=uuid4())
        fb = registry.submit_feedback(
            feedback_type=FeedbackType.CONFUSION,
            severity=FeedbackSeverity.LOW,
            message="Not sure how to use this feature",
            tester_id=tester.tester_id,
        )
        assert fb.tester_id == tester.tester_id

    def test_feedback_safety_concern_type(self):
        """Safety concern feedback type exists."""
        registry = BetaRegistry()
        fb = registry.submit_feedback(
            feedback_type=FeedbackType.SAFETY_CONCERN,
            severity=FeedbackSeverity.CRITICAL,
            message="User data appears to be shared across organizations",
        )
        assert fb.feedback_type == FeedbackType.SAFETY_CONCERN
        assert fb.severity == FeedbackSeverity.CRITICAL

    def test_feedback_no_raw_emails(self):
        """Feedback must not contain raw email addresses (policy)."""
        registry = BetaRegistry()
        fb = registry.submit_feedback(
            feedback_type=FeedbackType.BUG,
            severity=FeedbackSeverity.LOW,
            message="Error on user profile page",
        )
        assert "@" not in fb.message
        assert "password" not in fb.message.lower()

    def test_feedback_multiple_triage_levels(self):
        """Feedback can be triaged by severity level."""
        registry = BetaRegistry()
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.LOW, "Minor UI glitch")
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.MEDIUM, "Button not working")
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.HIGH, "Login broken")
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.CRITICAL, "Data leak")
        counts = registry.feedback_count_by_severity()
        assert counts.get("low") == 1
        assert counts.get("medium") == 1
        assert counts.get("high") == 1
        assert counts.get("critical") == 1

    def test_feedback_correlation_with_tester(self):
        """Feedback can be correlated with a tester who has custom limits."""
        registry = BetaRegistry()
        limits = BetaTesterLimits(max_sessions_per_day=3)
        tester = registry.add_tester(
            email_hash="premium_tester",
            organization_id=uuid4(),
            limits=limits,
        )
        registry.activate_tester("premium_tester")
        fb = registry.submit_feedback(
            feedback_type=FeedbackType.VALUE,
            severity=FeedbackSeverity.MEDIUM,
            message="Great feature! Would love more sessions though.",
            tester_id=tester.tester_id,
            organization_id=tester.organization_id,
        )
        assert fb.tester_id == tester.tester_id
        assert fb.feedback_type == FeedbackType.VALUE
        assert registry.get_limits("premium_tester").max_sessions_per_day == 3


class TestBetaSupportTriage:
    """Support triage flow tests."""

    def setup_method(self):
        reset_beta_registry()

    def test_feedback_critical_escalation(self):
        """Critical severity feedback can be identified for escalation."""
        registry = BetaRegistry()
        registry.submit_feedback(
            FeedbackType.BUG,
            FeedbackSeverity.CRITICAL,
            "Cannot access any beta features",
        )
        critical = registry.list_feedback(severity=FeedbackSeverity.CRITICAL)
        assert len(critical) >= 1

    def test_feedback_type_filtering(self):
        """Feedback can be filtered by type for triage."""
        registry = BetaRegistry()
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.LOW, "Bug report")
        registry.submit_feedback(FeedbackType.VALUE, FeedbackSeverity.LOW, "Positive feedback")
        registry.submit_feedback(FeedbackType.MISSING_FEATURE, FeedbackSeverity.MEDIUM, "Need export")
        bugs = registry.list_feedback(feedback_type=FeedbackType.BUG)
        assert len(bugs) == 1
        assert bugs[0].feedback_type == FeedbackType.BUG

    def test_feedback_limit_cap(self):
        """Feedback listing respects the limit cap."""
        registry = BetaRegistry()
        for i in range(25):
            registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.LOW, f"Bug {i}")
        default_list = registry.list_feedback()
        assert len(default_list) == 25
        capped = registry.list_feedback(limit=5)
        assert len(capped) == 5
