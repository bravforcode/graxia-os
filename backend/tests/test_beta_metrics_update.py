"""Beta Metrics & Exit Criteria Tests — Phase 20 Limited Beta Pilot.

Verifies that Phase 20 beta success metrics doc exists,
exit criteria are defined, and no security/privacy leak.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import settings


METRICS_DOC = Path(__file__).resolve().parents[2] / "docs" / "BETA_SUCCESS_METRICS.md"


class TestBetaMetricsDoc:
    """BETA_SUCCESS_METRICS.md must exist and contain required sections."""

    def test_metrics_doc_exists(self):
        assert METRICS_DOC.exists(), "BETA_SUCCESS_METRICS.md is missing"

    def test_metrics_doc_has_usage_metrics(self):
        content = METRICS_DOC.read_text()
        assert "Usage Metrics" in content

    def test_metrics_doc_has_exit_criteria(self):
        content = METRICS_DOC.read_text()
        assert "Exit Criteria" in content

    def test_metrics_doc_has_security_gates(self):
        content = METRICS_DOC.read_text()
        assert "Security Gates" in content

    def test_metrics_doc_has_quality_gates(self):
        content = METRICS_DOC.read_text()
        assert "Quality Gates" in content


class TestBetaMetricsContent:
    """BETA_SUCCESS_METRICS.md must contain required metric areas."""

    def test_metrics_doc_mentions_approval_acceptance(self):
        content = METRICS_DOC.read_text()
        assert "Approval Acceptance Rate" in content

    def test_metrics_doc_mentions_kill_switch(self):
        content = METRICS_DOC.read_text()
        assert "kill switch" in content.lower()

    def test_metrics_doc_mentions_operator_time(self):
        content = METRICS_DOC.read_text()
        assert "Operator" in content

    def test_metrics_doc_mentions_cross_org(self):
        content = METRICS_DOC.read_text()
        assert "cross-org" in content.lower()


class TestBetaMetricsSecrets:
    """Metrics doc must not contain secrets."""

    def test_metrics_doc_no_secrets(self):
        content = METRICS_DOC.read_text().lower()
        forbidden = ["sk_live", "sk_test", "api_key", "secret_key", "encryption_key"]
        for pattern in forbidden:
            assert pattern not in content, f"Secret pattern found in metrics doc: {pattern}"

    def test_metrics_doc_no_config_values(self):
        content = METRICS_DOC.read_text()
        assert "DATABASE_URL" not in content
        assert "POSTGRES_PASSWORD" not in content


class TestBetaMetricsCoverage:
    """Beta metrics doc must be referenced in readiness checks."""

    @pytest.mark.asyncio
    async def test_limited_beta_pilot_readiness_checks_metrics_doc(self, async_client):
        """Limited beta pilot readiness must check that BETA_SUCCESS_METRICS.md exists."""
        resp = await async_client.get("/api/v1/health/readiness/limited-beta-pilot")
        data = resp.json()
        checks = data.get("checks", {})
        # The check should reference that beta_metrics_exists is checked
        assert "beta_metrics_exists" in checks

    @pytest.mark.asyncio
    async def test_limited_beta_pilot_ready_is_false(self, async_client):
        """The aggregated limited_beta_pilot_ready boolean must be False.
        
        During Phase 20, the pilot is not ready because no testers are configured,
        kill switch is on, and LIMITED_BETA_PILOT_READY flag is False.
        """
        resp = await async_client.get("/api/v1/health/readiness/limited-beta-pilot")
        data = resp.json()
        assert data.get("limited_beta_pilot_ready") is False


class TestProductionReadyStillFalse:
    """Production readiness must remain false throughout Phase 20."""

    def test_production_ready_false(self):
        assert settings.PRODUCTION_READY is False

    def test_live_providers_disabled(self):
        assert settings.ALLOW_LIVE_STRIPE is False
        assert settings.ALLOW_REAL_EMAIL_SEND is False
        assert settings.ALLOW_REAL_GOOGLE_MUTATION is False
        assert settings.ALLOW_REAL_LLM_CALLS is False
        assert settings.ALLOW_PRODUCTION_DB is False

    def test_no_live_payment_mode_true(self):
        assert settings.NO_LIVE_PAYMENT_MODE is True

    def test_kill_switch_active(self):
        assert settings.KILL_SWITCH_ALL_EXTERNAL_BETA is True
