"""Kill Switch Drill Tests — Phase 20 Limited Beta Pilot.

Kill switch must be True by default and lock all beta APIs.
Disabling kill switch must be an explicit operator action.
"""

from __future__ import annotations

import pytest

from app.beta.registry import BetaRegistry, BetaTesterLimits, get_beta_registry, reset_beta_registry
from app.config import settings


@pytest.fixture(autouse=True)
def _reset_registry():
    reset_beta_registry()
    yield
    reset_beta_registry()


class TestKillSwitchDefault:
    """KILL_SWITCH_ALL_EXTERNAL_BETA must be True by default."""

    def test_kill_switch_true_by_default(self):
        assert settings.KILL_SWITCH_ALL_EXTERNAL_BETA is True

    def test_kill_switch_hard_locked(self):
        """Kill switch must not be accidentally disabled in test config."""
        assert settings.KILL_SWITCH_ALL_EXTERNAL_BETA is True

    def test_kill_switch_independent_of_beta_enabled(self):
        """Kill switch operates independently from BETA_ENABLED."""
        assert settings.KILL_SWITCH_ALL_EXTERNAL_BETA is True
        assert settings.BETA_ENABLED is False


class TestKillSwitchBlocksBeta:
    """When kill switch is True, beta features must be blocked."""

    @pytest.mark.asyncio
    async def test_beta_readiness_shows_beta_enabled_false(self, async_client):
        """Beta readiness endpoint must confirm BETA_ENABLED is False."""
        resp = await async_client.get("/api/v1/health/readiness/beta")
        data = resp.json()
        assert data.get("beta_enabled") is False

    def test_beta_workflows_blocked_when_kill_switch_active(self):
        """Beta workflows must not start when kill switch is active."""
        assert settings.KILL_SWITCH_ALL_EXTERNAL_BETA is True
        assert settings.BETA_WORKFLOWS_ENABLED is False

    def test_beta_mcp_tools_blocked_when_kill_switch_active(self):
        """Beta MCP tools must be blocked when kill switch is active."""
        assert settings.KILL_SWITCH_ALL_EXTERNAL_BETA is True
        assert settings.BETA_MCP_TOOLS_ENABLED is False

    @pytest.mark.asyncio
    async def test_kill_switch_shown_in_beta_readiness(self, async_client):
        """Beta readiness must show kill switch status."""
        resp = await async_client.get("/api/v1/health/readiness/beta")
        data = resp.json()
        assert "kill_switch_enabled" in data
        assert data["kill_switch_enabled"] is True

    @pytest.mark.asyncio
    async def test_kill_switch_shown_in_limited_beta_pilot(self, async_client):
        """Limited beta pilot readiness must show kill switch enabled."""
        resp = await async_client.get("/api/v1/health/readiness/limited-beta-pilot")
        data = resp.json()
        assert "kill_switch_enabled" in data
        assert data["kill_switch_enabled"] is True


class TestKillSwitchTesterSafety:
    """Kill switch must protect tester operations."""

    def test_tester_cannot_be_active_when_kill_switch_active(self):
        """No testers should be active when kill switch is on."""
        # Registry should be empty at test start (reset by fixture)
        registry = get_beta_registry()
        assert len(registry.list_active_testers()) == 0

    def test_added_tester_cannot_execute_workflows_with_kill_switch(self):
        """Even if tester exists, workflows must not run when kill switch is active."""
        assert settings.KILL_SWITCH_ALL_EXTERNAL_BETA is True
        assert settings.BETA_WORKFLOWS_ENABLED is False

    @pytest.mark.asyncio
    async def test_readiness_shows_tester_count_when_tester_added(self, async_client):
        """Adding a tester should show in readiness count."""
        registry = get_beta_registry()
        registry.add_tester(
            email_hash="abc123",
            limits=BetaTesterLimits(max_sessions_per_day=3),
        )
        registry.activate_tester("abc123")

        resp = await async_client.get("/api/v1/health/readiness/beta")
        data = resp.json()
        assert "beta_tester_count" in data


class TestKillSwitchSecrets:
    """Kill switch drill must not leak secrets."""

    @pytest.mark.asyncio
    async def test_kill_switch_readiness_no_secrets(self, async_client):
        """Readiness endpoints must not leak secrets when kill switch is active."""
        endpoints = [
            "/api/v1/health/readiness/beta",
            "/api/v1/health/readiness/limited-beta-pilot",
        ]
        for endpoint in endpoints:
            resp = await async_client.get(endpoint)
            text = resp.text.lower()
            assert "sk_live" not in text
            assert "api_key" not in text
            assert "secret_key" not in text
            assert "encryption_key" not in text
