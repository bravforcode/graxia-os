"""Human Approval Reality Drill — Phase 20 Limited Beta Pilot.

Builds on the existing Phase 19 approval drill with more realistic scenarios.
Every test verifies: no auto-send, no auto-publish, no real charge.
"""

from __future__ import annotations

import pytest

from app.config import settings


class TestApprovalDrillScenario1OpportunityScout:
    """Scenario: AI scouts an opportunity and recommends action."""

    def test_opportunity_scout_blocked_by_production_gate(self):
        """Opportunity scout recommendations must be blocked by production gate."""
        assert settings.PRODUCTION_READY is False
        assert settings.ALLOW_REAL_EMAIL_SEND is False

    @pytest.mark.asyncio
    async def test_opportunity_scout_readiness_proves_no_live_outreach(self, async_client):
        """Production gate must show email sending is blocked."""
        resp = await async_client.get("/api/v1/health/readiness/production")
        data = resp.json()
        checks = data.get("checks", {})
        assert checks.get("real_email_send_blocked") is True

    def test_opportunity_scout_draft_only_default(self):
        """OUTREACH_AUTOSEND_ENABLED must be False."""
        assert settings.OUTREACH_AUTOSEND_ENABLED is False


class TestApprovalDrillScenario2DraftFollowUp:
    """Scenario: AI drafts a follow-up message for a lead."""

    def test_draft_follow_up_no_auto_send(self):
        """Follow-up drafts must not auto-send."""
        assert settings.OUTREACH_AUTOSEND_ENABLED is False
        assert settings.OUTREACH_MAX_PER_DAY <= 5

    @pytest.mark.asyncio
    async def test_draft_follow_up_blocked_by_email_gate(self, async_client):
        """Email gate must show sending is blocked."""
        resp = await async_client.get("/api/v1/health/readiness/production")
        data = resp.json()
        checks = data.get("checks", {})
        assert checks.get("real_email_send_blocked") is True


class TestApprovalDrillScenario3ContentPublish:
    """Scenario: AI generates content for publishing."""

    def test_content_publish_blocked(self):
        """No auto-publish mechanism should be enabled."""
        assert settings.BETA_PUBLIC_FUNNEL_ENABLED is False
        assert settings.OUTREACH_AUTOSEND_ENABLED is False

    @pytest.mark.asyncio
    async def test_content_publish_readiness_shows_blocked(self, async_client):
        """Beta readiness must show public funnel is disabled."""
        resp = await async_client.get("/api/v1/health/readiness/beta")
        data = resp.json()
        # beta_enabled should be False, showing beta features are locked
        assert data.get("beta_enabled") is False


class TestApprovalDrillScenario4WorkflowExecution:
    """Scenario: AI workflow executes and produces output."""

    def test_workflow_execution_non_production(self):
        """Workflows must not run in production mode."""
        assert settings.PRODUCTION_READY is False
        assert settings.BETA_WORKFLOWS_ENABLED is False

    @pytest.mark.asyncio
    async def test_workflow_execution_readiness_no_live_calls(self, async_client):
        """Readiness must show real LLM calls are blocked."""
        resp = await async_client.get("/api/v1/health/readiness/production")
        data = resp.json()
        checks = data.get("checks", {})
        assert checks.get("real_llm_calls_blocked") is True


class TestApprovalDrillScenario5PaymentCharge:
    """Scenario: AI attempts to process a payment."""

    def test_payment_charge_blocked_by_no_live_payment_mode(self):
        """NO_LIVE_PAYMENT_MODE must block all payment attempts."""
        assert settings.NO_LIVE_PAYMENT_MODE is True

    def test_payment_charge_blocked_by_live_stripe_gate(self):
        """ALLOW_LIVE_STRIPE must be False, blocking real charges."""
        assert settings.ALLOW_LIVE_STRIPE is False

    @pytest.mark.asyncio
    async def test_payment_charge_readiness_shows_stripe_blocked(self, async_client):
        """Production readiness must show Stripe is blocked."""
        resp = await async_client.get("/api/v1/health/readiness/production")
        data = resp.json()
        checks = data.get("checks", {})
        assert checks.get("live_stripe_blocked") is True

    def test_payment_charge_no_stripe_secret_key(self):
        """Must not have a live Stripe secret key configured."""
        key = (settings.STRIPE_SECRET_KEY or "").strip()
        assert not key or not key.startswith("sk_live_")


class TestApprovalDrillSecretSafety:
    """Approval drill must not leak secrets."""

    @pytest.mark.asyncio
    async def test_all_readiness_endpoints_no_secrets(self, async_client):
        """All health/readiness responses must not contain secret patterns."""
        endpoints = [
            "/api/v1/health",
            "/api/v1/health/readiness",
            "/api/v1/health/readiness/staging",
            "/api/v1/health/readiness/production",
            "/api/v1/health/readiness/beta",
            "/api/v1/health/readiness/limited-beta-pilot",
        ]
        secret_patterns = [
            "sk_live_",
            "sk_test_",
            "RESEND_API_KEY",
            "GOOGLE_CLIENT_SECRET",
            "STRIPE_SECRET_KEY",
            "POSTGRES_PASSWORD",
            "ENCRYPTION_KEY",
        ]
        for endpoint in endpoints:
            resp = await async_client.get(endpoint)
            text = resp.text.lower()
            for pattern in secret_patterns:
                assert pattern.lower() not in text, f"Secret leaked at {endpoint}: {pattern}"
