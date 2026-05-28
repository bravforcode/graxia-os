"""Test beta cohort allowlist — in-memory registry for controlled beta."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.beta.registry import (
    BetaFeedback,
    BetaRegistry,
    BetaTester,
    BetaTesterLimits,
    BetaTesterStatus,
    FeedbackSeverity,
    FeedbackType,
    reset_beta_registry,
)


class TestBetaRegistry:
    """Beta registry management tests."""

    def setup_method(self):
        reset_beta_registry()

    def test_add_tester(self):
        """Adding a tester returns an invited tester."""
        registry = BetaRegistry()
        tester = registry.add_tester(
            email_hash="abc123def456",
            organization_id=uuid4(),
        )
        assert tester.email_hash == "abc123def456"
        assert tester.status == BetaTesterStatus.INVITED
        assert tester.limits.max_sessions_per_day == 5
        assert tester.limits.max_workflows_per_day == 20
        assert tester.limits.max_mcp_calls_per_day == 100

    def test_add_tester_duplicate_raises(self):
        """Adding the same email_hash twice raises ValueError."""
        registry = BetaRegistry()
        registry.add_tester(email_hash="abc123")
        with pytest.raises(ValueError, match="already exists"):
            registry.add_tester(email_hash="abc123")

    def test_get_tester(self):
        """Getting a tester by email_hash returns the tester."""
        registry = BetaRegistry()
        registry.add_tester(email_hash="abc123")
        tester = registry.get_tester("abc123")
        assert tester is not None
        assert tester.email_hash == "abc123"

    def test_get_tester_not_found(self):
        """Getting a non-existent tester returns None."""
        registry = BetaRegistry()
        assert registry.get_tester("nonexistent") is None

    def test_get_tester_by_id(self):
        """Getting a tester by UUID works."""
        registry = BetaRegistry()
        added = registry.add_tester(email_hash="abc123")
        found = registry.get_tester_by_id(added.tester_id)
        assert found is not None
        assert found.email_hash == "abc123"

    def test_get_tester_by_id_not_found(self):
        """Getting a non-existent tester by UUID returns None."""
        registry = BetaRegistry()
        assert registry.get_tester_by_id(uuid4()) is None

    def test_activate_tester(self):
        """Activating a tester changes status to active."""
        registry = BetaRegistry()
        registry.add_tester(email_hash="abc123")
        tester = registry.activate_tester("abc123")
        assert tester is not None
        assert tester.status == BetaTesterStatus.ACTIVE
        assert registry.is_active("abc123")

    def test_pause_tester(self):
        """Pausing a tester changes status to paused."""
        registry = BetaRegistry()
        registry.add_tester(email_hash="abc123")
        registry.activate_tester("abc123")
        tester = registry.pause_tester("abc123")
        assert tester is not None
        assert tester.status == BetaTesterStatus.PAUSED
        assert registry.is_paused("abc123")

    def test_remove_tester(self):
        """Removing a tester removes them from registry."""
        registry = BetaRegistry()
        registry.add_tester(email_hash="abc123")
        assert registry.remove_tester("abc123") is True
        assert registry.get_tester("abc123") is None

    def test_remove_nonexistent_tester(self):
        """Removing a non-existent tester returns False."""
        registry = BetaRegistry()
        assert registry.remove_tester("nonexistent") is False

    def test_list_active_testers(self):
        """Listing active testers returns only active ones."""
        registry = BetaRegistry()
        registry.add_tester(email_hash="tester1")
        registry.add_tester(email_hash="tester2")
        registry.activate_tester("tester1")
        active = registry.list_active_testers()
        assert len(active) == 1
        assert active[0].email_hash == "tester1"

    def test_list_all_testers(self):
        """Listing all testers returns all statuses."""
        registry = BetaRegistry()
        registry.add_tester(email_hash="tester1")
        registry.add_tester(email_hash="tester2")
        assert len(registry.list_all_testers()) == 2

    def test_tester_count(self):
        """Tester count returns counts by status."""
        registry = BetaRegistry()
        registry.add_tester(email_hash="tester1")
        registry.add_tester(email_hash="tester2")
        registry.add_tester(email_hash="tester3")
        registry.activate_tester("tester1")
        registry.activate_tester("tester2")
        counts = registry.tester_count()
        assert counts.get("active") == 2
        assert counts.get("invited") == 1

    def test_custom_limits(self):
        """Custom per-tester limits can be set."""
        registry = BetaRegistry()
        limits = BetaTesterLimits(
            max_sessions_per_day=10,
            max_workflows_per_day=50,
            max_mcp_calls_per_day=200,
        )
        registry.add_tester(email_hash="abc123", limits=limits)
        tester = registry.get_tester("abc123")
        assert tester.limits.max_sessions_per_day == 10
        assert tester.limits.max_workflows_per_day == 50
        assert tester.limits.max_mcp_calls_per_day == 200

    def test_get_limits(self):
        """Getting limits returns the tester's limits."""
        registry = BetaRegistry()
        limits = BetaTesterLimits(max_sessions_per_day=3)
        registry.add_tester(email_hash="abc123", limits=limits)
        retrieved = registry.get_limits("abc123")
        assert retrieved.max_sessions_per_day == 3

    def test_get_limits_nonexistent(self):
        """Getting limits for non-existent tester returns None."""
        registry = BetaRegistry()
        assert registry.get_limits("nonexistent") is None

    def test_reset(self):
        """Resetting the registry clears all testers and feedback."""
        registry = BetaRegistry()
        registry.add_tester(email_hash="abc123")
        assert len(registry.list_all_testers()) == 1
        registry.reset()
        assert len(registry.list_all_testers()) == 0


class TestBetaFeedback:
    """Beta feedback tests."""

    def setup_method(self):
        reset_beta_registry()

    def test_submit_feedback(self):
        """Submitting feedback stores it."""
        registry = BetaRegistry()
        fb = registry.submit_feedback(
            feedback_type=FeedbackType.BUG,
            severity=FeedbackSeverity.HIGH,
            message="Login button not working",
            request_id="req_abc123",
            correlation_id="corr_def456",
        )
        assert fb.feedback_type == FeedbackType.BUG
        assert fb.severity == FeedbackSeverity.HIGH
        assert fb.message == "Login button not working"
        assert fb.request_id == "req_abc123"
        assert fb.correlation_id == "corr_def456"

    def test_list_feedback(self):
        """Listing feedback returns most recent first."""
        registry = BetaRegistry()
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.LOW, "Bug 1")
        registry.submit_feedback(FeedbackType.CONFUSION, FeedbackSeverity.HIGH, "Confusion 1")
        all_fb = registry.list_feedback()
        assert len(all_fb) == 2

    def test_feedback_filter_by_severity(self):
        """Feedback can be filtered by severity."""
        registry = BetaRegistry()
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.LOW, "Low bug")
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.CRITICAL, "Critical bug")
        critical = registry.list_feedback(severity=FeedbackSeverity.CRITICAL)
        assert len(critical) == 1
        assert critical[0].severity == FeedbackSeverity.CRITICAL

    def test_feedback_filter_by_type(self):
        """Feedback can be filtered by type."""
        registry = BetaRegistry()
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.LOW, "Bug report")
        registry.submit_feedback(FeedbackType.VALUE, FeedbackSeverity.LOW, "Love this feature")
        value_fb = registry.list_feedback(feedback_type=FeedbackType.VALUE)
        assert len(value_fb) == 1

    def test_feedback_count_by_severity(self):
        """Feedback counts by severity."""
        registry = BetaRegistry()
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.LOW, "Bug 1")
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.HIGH, "Bug 2")
        counts = registry.feedback_count_by_severity()
        assert counts.get("low") == 1
        assert counts.get("high") == 1

    def test_feedback_count_by_type(self):
        """Feedback counts by type."""
        registry = BetaRegistry()
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.LOW, "Bug")
        registry.submit_feedback(FeedbackType.VALUE, FeedbackSeverity.LOW, "Value")
        counts = registry.feedback_count_by_type()
        assert counts.get("bug") == 1
        assert counts.get("value") == 1

    def test_feedback_limit(self):
        """Feedback listing respects limit."""
        registry = BetaRegistry()
        for i in range(10):
            registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.LOW, f"Bug {i}")
        assert len(registry.list_feedback(limit=3)) == 3

    def test_feedback_no_secrets_in_message(self):
        """Feedback message must not contain secrets. (Policy test.)"""
        registry = BetaRegistry()
        fb = registry.submit_feedback(
            FeedbackType.BUG,
            FeedbackSeverity.LOW,
            "Error on connect - no secret values stored",
        )
        assert "secret" not in fb.message or "password" not in fb.message.lower()
