from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@pytest.mark.asyncio
async def test_token_roi_summary_mcp_api_exposes_dashboard_metrics(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    me_response = await async_client.get("/api/v1/auth/me")
    user_id = UUID(me_response.json()["id"])
    organization_id = str(
        (await db_session.execute(select(User.organization_id).where(User.id == user_id))).scalar_one()
    )

    # Test env resolves tenant from this header; default is the local dev org.
    async_client.headers["X-Graxia-Org-Id"] = organization_id
    response = await async_client.post(
        "/api/v1/mcp/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "organization_id": organization_id,
                "name": "get_token_roi_summary",
                "arguments": {
                    "organization_id": organization_id,
                    "tokens_saved": 2500,
                    "retry_count": 1,
                    "retry_token_cost": 150,
                    "human_correction_count": 1,
                    "human_correction_cost": 200,
                    "quality_gate_passed": True,
                    "critical_context_lost": False,
                    "compression_ratio": 0.72,
                    "cache_hit_rate": 0.4,
                    "quality_gate_failures": 1,
                    "auto_escalations": 2,
                    "stale_context_incidents": 1,
                },
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["tokens_saved"] == 2500
    assert payload["data"]["cache_credit"] == 100
    assert payload["data"]["quality_penalty"] == 100
    assert payload["data"]["escalation_penalty"] == 150
    assert payload["data"]["stale_context_penalty"] == 200
    assert payload["data"]["net_roi"] == 1800
    assert payload["data"]["recommendation"] == "review_compression"
    assert payload["meta"]["organization_id"] == organization_id
