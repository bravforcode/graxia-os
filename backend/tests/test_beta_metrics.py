"""Test beta metrics and exit criteria documentation."""
from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestBetaMetrics:
    """Beta metrics documentation checks."""

    def test_beta_metrics_doc_exists(self):
        """BETA_SUCCESS_METRICS.md must exist."""
        path = PROJECT_ROOT / "docs" / "BETA_SUCCESS_METRICS.md"
        assert path.exists(), f"Missing: {path}"

    def test_beta_metrics_has_required_metrics(self):
        """BETA_SUCCESS_METRICS.md must include required metrics categories."""
        path = PROJECT_ROOT / "docs" / "BETA_SUCCESS_METRICS.md"
        content = path.read_text(encoding="utf-8")
        required_terms = [
            "activation rate",
            "task completion",
            "approval acceptance",
            "safe error",
            "rate-limit",
            "retention",
        ]
        for term in required_terms:
            assert term.lower() in content.lower(), f"Missing metric: {term}"

    def test_beta_metrics_has_exit_criteria(self):
        """BETA_SUCCESS_METRICS.md must include exit criteria."""
        path = PROJECT_ROOT / "docs" / "BETA_SUCCESS_METRICS.md"
        content = path.read_text(encoding="utf-8")
        assert "Exit Criteria" in content or "exit criteria" in content.lower()

    def test_beta_metrics_coverage(self):
        """BETA_SUCCESS_METRICS.md must include coverage metrics."""
        path = PROJECT_ROOT / "docs" / "BETA_SUCCESS_METRICS.md"
        content = path.read_text(encoding="utf-8")
        assert "coverage" in content.lower() or "count" in content.lower()

    def test_beta_metrics_not_secrets(self):
        """BETA_SUCCESS_METRICS.md must not contain real credential patterns."""
        path = PROJECT_ROOT / "docs" / "BETA_SUCCESS_METRICS.md"
        content = path.read_text(encoding="utf-8")
        forbidden = ["sk_live_", "-----BEGIN "]
        for term in forbidden:
            assert term not in content.lower(), f"Credential pattern '{term}' found in doc"


class TestBetaRegistryMetrics:
    """Beta registry provides metrics data."""

    def test_registry_tester_count(self):
        """Registry provides tester count breakdown."""
        from app.beta.registry import BetaRegistry, reset_beta_registry
        reset_beta_registry()
        registry = BetaRegistry()
        registry.add_tester(email_hash="tester1")
        registry.add_tester(email_hash="tester2")
        registry.activate_tester("tester1")
        counts = registry.tester_count()
        assert "active" in counts
        assert "invited" in counts

    def test_registry_feedback_counts(self):
        """Registry provides feedback counts."""
        from app.beta.registry import BetaRegistry, FeedbackType, FeedbackSeverity, reset_beta_registry
        reset_beta_registry()
        registry = BetaRegistry()
        registry.submit_feedback(FeedbackType.BUG, FeedbackSeverity.HIGH, "Bug!")
        registry.submit_feedback(FeedbackType.VALUE, FeedbackSeverity.LOW, "Good!")
        sev_counts = registry.feedback_count_by_severity()
        type_counts = registry.feedback_count_by_type()
        assert sev_counts.get("high") == 1
        assert sev_counts.get("low") == 1
        assert type_counts.get("bug") == 1
        assert type_counts.get("value") == 1
