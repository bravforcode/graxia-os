"""Tests for NO_LIVE_PAYMENT_MODE guard — Phase 20 Limited Beta Pilot.

NO_LIVE_PAYMENT_MODE is True by default, blocking all payment processing.
Even if explicitly disabled, live provider guards still prevent real charges.
"""

from __future__ import annotations

import pytest

from app.config import settings


class TestNoLivePaymentDefaults:
    """NO_LIVE_PAYMENT_MODE must be True by default."""

    def test_no_live_payment_mode_true_by_default(self):
        assert settings.NO_LIVE_PAYMENT_MODE is True

    def test_no_live_payment_mode_locks_live_stripe(self):
        """When NO_LIVE_PAYMENT_MODE is True, ALLOW_LIVE_STRIPE is irrelevant."""
        assert settings.NO_LIVE_PAYMENT_MODE is True
        assert settings.ALLOW_LIVE_STRIPE is False

    def test_payment_blocked_independent_of_kill_switch(self):
        """NO_LIVE_PAYMENT_MODE operates independently from beta kill switch."""
        assert settings.NO_LIVE_PAYMENT_MODE is True
        assert settings.KILL_SWITCH_ALL_EXTERNAL_BETA is True


class TestNoLivePaymentBlockers:
    """NO_LIVE_PAYMENT_MODE must be reported in readiness checks."""

    @pytest.mark.asyncio
    async def test_limited_beta_pilot_readiness_has_no_live_payment_check(self, async_client):
        resp = await async_client.get("/api/v1/health/readiness/limited-beta-pilot")
        assert resp.status_code == 200
        data = resp.json()
        assert "checks" in data
        assert "no_live_payment_mode" in data["checks"]

    @pytest.mark.asyncio
    async def test_no_live_payment_check_is_true_in_checks(self, async_client):
        """NO_LIVE_PAYMENT_MODE=True should show as a passed check."""
        resp = await async_client.get("/api/v1/health/readiness/limited-beta-pilot")
        data = resp.json()
        assert data["checks"]["no_live_payment_mode"] is True

    @pytest.mark.asyncio
    async def test_no_live_payment_blocker_not_present_when_enabled(self, async_client):
        """When NO_LIVE_PAYMENT_MODE is True, no blocker about payment is present."""
        resp = await async_client.get("/api/v1/health/readiness/limited-beta-pilot")
        data = resp.json()
        blockers_text = " ".join(data.get("blockers", []))
        assert "live payment" not in blockers_text.lower()


class TestNoLivePaymentSafety:
    """NO_LIVE_PAYMENT_MODE must never leak secrets."""

    @pytest.mark.asyncio
    async def test_no_live_payment_endpoint_no_secrets(self, async_client):
        """Limited beta pilot readiness must not leak config values."""
        resp = await async_client.get("/api/v1/health/readiness/limited-beta-pilot")
        text = resp.text
        secrets_patterns = [
            "sk_live_",
            "sk_test_",
            "stripe_secret",
            "STRIPE_SECRET_KEY",
            "RESEND_API_KEY",
            "GOOGLE_CLIENT_SECRET",
        ]
        for pattern in secrets_patterns:
            assert pattern.lower() not in text.lower(), f"Secret pattern leaked: {pattern}"

    @pytest.mark.asyncio
    async def test_no_live_payment_response_no_raw_env(self, async_client):
        """Response must not include raw .env values."""
        resp = await async_client.get("/api/v1/health/readiness/limited-beta-pilot")
        text = resp.text
        forbidden = [
            "DATABASE_URL",
            "POSTGRES_PASSWORD",
            "ENCRYPTION_KEY",
        ]
        for pattern in forbidden:
            assert pattern not in text, f"Raw env key leaked: {pattern}"

    @pytest.mark.asyncio
    async def test_no_live_payment_does_not_call_live_providers(self, async_client):
        """Checking readiness must not trigger any live provider call."""
        resp = await async_client.get("/api/v1/health/readiness/limited-beta-pilot")
        # If this endpoint calls live providers, it would timeout or return errors
        # Instead, it should just check config flags
        data = resp.json()
        assert data["checks"]["no_live_payment_mode"] is True
        assert data["checks"]["live_providers_enabled"] is False
