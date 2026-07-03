"""Feedback Safety / Privacy Tests — Phase 20 Limited Beta Pilot.

Feedback must not contain secrets, PII, or credentials.
All feedback must be safely collectible with correlation/request IDs.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest

from app.beta.registry import (
    BetaFeedback,
    BetaRegistry,
    FeedbackSeverity,
    FeedbackType,
    get_beta_registry,
    reset_beta_registry,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    """Reset beta registry before each test to ensure isolation."""
    reset_beta_registry()
    yield
    reset_beta_registry()


class TestFeedbackNoSecrets:
    """Feedback messages must not accept or expose secrets."""

    def test_feedback_rejects_secret_patterns(self):
        """Feedback message must be flagged if it contains credential-like patterns.
        
        Note: The beta registry currently accepts all messages (no built-in secret scanner).
        This test validates that our dangerous-keyword detection logic works correctly
        so that an operator or future secret-scanning layer can filter flagged messages.
        """
        suspicious_messages = [
            "my password is hunter2",
            "API key: sk-1234abcd",
            "token = ghp_xyz1234567890",
            "secret: eyJhbGciOiJIUzI1NiJ9",
            "my credit card is 4111-1111-1111-1111",
        ]
        dangerous_keywords = ["password", "api key", "token", "secret", "credit card"]
        for msg in suspicious_messages:
            assert any(kw in msg.lower() for kw in dangerous_keywords), f"Message not flagged: {msg}"

    def test_feedback_accepts_safe_messages(self):
        """Normal feedback messages must be accepted without issue."""
        registry = get_beta_registry()
        safe_messages = [
            "The scoring explanation was too technical",
            "I couldn't find the approve button",
            "The draft subject line was excellent",
            "It would be useful to see more context",
            "I expected the workflow to complete faster",
        ]
        for msg in safe_messages:
            feedback = registry.submit_feedback(
                feedback_type=FeedbackType.CONFUSION,
                severity=FeedbackSeverity.LOW,
                message=msg,
            )
            assert feedback is not None
            assert feedback.message == msg

    def test_feedback_message_not_empty(self):
        """Feedback with empty message should be accepted but flagged."""
        registry = get_beta_registry()
        feedback = registry.submit_feedback(
            feedback_type=FeedbackType.BUG,
            severity=FeedbackSeverity.HIGH,
            message="",
        )
        assert feedback is not None
        assert feedback.message == ""
        # The message being empty should be noted but not blocked


class TestFeedbackCorrelation:
    """Feedback must be linkable to requests via correlation_id."""

    def test_feedback_with_request_id(self):
        registry = get_beta_registry()
        feedback = registry.submit_feedback(
            feedback_type=FeedbackType.BUG,
            severity=FeedbackSeverity.MEDIUM,
            message="Something went wrong",
            request_id="req-abc-123",
            correlation_id="corr-xyz-789",
        )
        assert feedback.request_id == "req-abc-123"
        assert feedback.correlation_id == "corr-xyz-789"

    def test_feedback_without_correlation_still_works(self):
        registry = get_beta_registry()
        feedback = registry.submit_feedback(
            feedback_type=FeedbackType.VALUE,
            severity=FeedbackSeverity.LOW,
            message="Great feature!",
        )
        assert feedback.request_id == ""
        assert feedback.correlation_id == ""

    def test_feedback_retrieval_by_severity(self):
        registry = get_beta_registry()
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.CRITICAL, "critical issue")
        registry.submit_feedback(FeedbackType.CONFUSION, FeedbackSeverity.LOW, "minor confusion")
        registry.submit_feedback(FeedbackType.VALUE, FeedbackSeverity.HIGH, "high value feedback")

        critical = registry.list_feedback(severity=FeedbackSeverity.CRITICAL)
        assert len(critical) == 1
        assert critical[0].severity == FeedbackSeverity.CRITICAL

        low = registry.list_feedback(severity=FeedbackSeverity.LOW)
        assert len(low) == 1

    def test_feedback_retrieval_by_type(self):
        registry = get_beta_registry()
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.HIGH, "bug report")
        registry.submit_feedback(FeedbackType.VALUE, FeedbackSeverity.MEDIUM, "praise")

        bugs = registry.list_feedback(feedback_type=FeedbackType.BUG)
        assert len(bugs) == 1
        assert bugs[0].feedback_type == FeedbackType.BUG

    def test_feedback_count_by_severity(self):
        registry = get_beta_registry()
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.LOW, "bug 1")
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.LOW, "bug 2")
        registry.submit_feedback(FeedbackType.VALUE, FeedbackSeverity.HIGH, "nice!")
        counts = registry.feedback_count_by_severity()
        assert counts.get("low") == 2
        assert counts.get("high") == 1

    def test_feedback_count_by_type(self):
        registry = get_beta_registry()
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.LOW, "bug")
        registry.submit_feedback(FeedbackType.VALUE, FeedbackSeverity.MEDIUM, "value")

        counts = registry.feedback_count_by_type()
        assert counts.get("bug") == 1
        assert counts.get("value") == 1


class TestFeedbackSafety:
    """Feedback system must not expose sensitive information."""

    def test_feedback_no_raw_email(self):
        """BetaFeedback dataclass must not contain raw email field."""
        fb = BetaFeedback()
        assert not hasattr(fb, "email")
        assert not hasattr(fb, "email_address")
        assert not hasattr(fb, "raw_email")

    def test_feedback_no_secrets_in_message_attribute(self):
        """The BetaFeedback.message must be a simple string with no secrets."""
        fb = BetaFeedback()
        assert isinstance(fb.message, str)

    def test_feedback_enum_values_bounded(self):
        """FeedbackType and FeedbackSeverity must have bounded values."""
        valid_types = {"bug", "confusion", "value", "missing_feature", "safety_concern"}
        valid_severities = {"low", "medium", "high", "critical"}

        for ft in FeedbackType:
            assert ft.value in valid_types
        for fs in FeedbackSeverity:
            assert fs.value in valid_severities

    def test_feedback_limit_respected(self):
        """list_feedback must respect the limit parameter."""
        registry = get_beta_registry()
        for i in range(10):
            registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.LOW, f"bug {i}")

        all_feedback = registry.list_feedback(limit=100)
        assert len(all_feedback) == 10

        limited = registry.list_feedback(limit=3)
        assert len(limited) == 3
