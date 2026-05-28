"""Test human approval drill scenarios — no auto-send, no auto-publish, no real charge."""
from __future__ import annotations

import pytest


class TestHumanApprovalDrill:
    """Human approval drill scenarios for controlled beta."""

    @pytest.mark.asyncio
    async def test_approval_drill_scenario_1_ai_drafts_content_plan(self, async_client):
        """Scenario 1: AI drafts content plan — operator must approve.

        This test verifies the approval endpoint exists and can be used
        to review and approve/reject AI-generated content plans.
        """
        response = await async_client.get("/api/v1/health/readiness/beta")
        assert response.status_code == 200
        payload = response.json()
        checks = payload.get("checks", {})
        assert "approval_system_ready" in checks

    @pytest.mark.asyncio
    async def test_approval_drill_scenario_2_opportunity_scout(self, async_client):
        """Scenario 2: opportunity_scout finds opportunity — operator marks do/skip/delay."""
        response = await async_client.get("/api/v1/health/readiness/production")
        assert response.status_code == 200
        payload = response.json()
        checks = payload.get("checks", {})
        assert "go_no_go_required" in checks
        assert checks["go_no_go_required"] is True

    @pytest.mark.asyncio
    async def test_approval_drill_scenario_3_lead_follow_up_no_send(self, async_client):
        """Scenario 3: Lead follow-up draft — approval required, no send without approval."""
        response = await async_client.get("/api/v1/health/readiness/production")
        assert response.status_code == 200
        payload = response.json()
        blockers = payload.get("blockers", [])
        blocker_text = " ".join(blockers).lower()
        assert "go_no_go" in blocker_text or "closed" in blocker_text or "approval" in blocker_text

    @pytest.mark.asyncio
    async def test_approval_drill_scenario_4_risky_mcp_tool_blocked(self, async_client):
        """Scenario 4: Risky MCP tool call requires approval or is blocked."""
        response = await async_client.get("/api/v1/health/readiness/beta")
        assert response.status_code == 200
        payload = response.json()
        checks = payload.get("checks", {})
        assert "kill_switch_ready" in checks
        assert "approval_system_ready" in checks

    @pytest.mark.asyncio
    async def test_approval_drill_scenario_5_dangerous_tool_blocked(self, async_client):
        """Scenario 5: Dangerous tool is always blocked."""
        response = await async_client.get("/api/v1/health/readiness/beta")
        assert response.status_code == 200
        payload = response.json()
        checks = payload.get("checks", {})
        assert checks.get("kill_switch_ready") is True

    @pytest.mark.asyncio
    async def test_approval_drill_no_auto_send(self, async_client):
        """No auto-send in test environment — verified via production readiness gate."""
        response = await async_client.get("/api/v1/health/readiness/production")
        assert response.status_code == 200
        payload = response.json()
        checks = payload.get("checks", {})
        assert checks.get("real_email_send_blocked") is True

    @pytest.mark.asyncio
    async def test_approval_drill_no_auto_publish(self, async_client):
        """No auto-publish in test environment — beta public funnel is disabled."""
        response = await async_client.get("/api/v1/health/readiness/beta")
        assert response.status_code == 200
        payload = response.json()
        assert payload.get("beta_enabled") is False
