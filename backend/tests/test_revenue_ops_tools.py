"""Tests for Phase 15 revenue-ops MCP tools."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

import app.mcp.tools  # noqa: F401
from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPAuthContext
from app.models.opportunity import Opportunity
from app.models.outcome_pattern import OutcomePattern


@pytest.mark.asyncio
async def test_get_high_score_opportunities_returns_ranked_items(db_session, default_org):
    low = Opportunity(
        id=uuid4(),
        organization_id=default_org.id,
        type="other",
        title="Low Score",
        total_score=Decimal("6.40"),
        status="found",
        found_at=datetime.now(UTC),
    )
    high = Opportunity(
        id=uuid4(),
        organization_id=default_org.id,
        type="competition",
        title="High Score",
        total_score=Decimal("9.20"),
        status="approved",
        decision="do_now",
        action_priority="do_now",
        found_at=datetime.now(UTC),
    )
    mid = Opportunity(
        id=uuid4(),
        organization_id=default_org.id,
        type="grant",
        title="Mid Score",
        total_score=Decimal("8.10"),
        status="scored",
        decision="ask_user",
        action_priority="queue",
        found_at=datetime.now(UTC),
    )
    db_session.add_all([low, high, mid])
    await db_session.commit()

    auth = MCPAuthContext.system(organization_id=str(default_org.id))
    resp = await mcp_registry.call_tool(
        "get_high_score_opportunities",
        {"organization_id": str(default_org.id), "threshold": 7.0, "limit": 10},
        auth=auth,
    )

    assert resp.ok is True
    assert resp.data["total"] == 2
    assert [item["title"] for item in resp.data["items"]] == ["High Score", "Mid Score"]
    assert resp.data["items"][0]["total_score"] == "9.20"


@pytest.mark.asyncio
async def test_get_outcome_patterns_summary_scopes_through_opportunity_org(db_session, default_org):
    opp_a = Opportunity(
        id=uuid4(),
        organization_id=default_org.id,
        type="freelance",
        title="Opportunity A",
        total_score=Decimal("8.60"),
        status="approved",
        found_at=datetime.now(UTC),
    )
    opp_b = Opportunity(
        id=uuid4(),
        organization_id=default_org.id,
        type="grant",
        title="Opportunity B",
        total_score=Decimal("7.90"),
        status="rejected",
        found_at=datetime.now(UTC),
    )
    db_session.add_all([opp_a, opp_b])
    await db_session.commit()

    patterns = [
        OutcomePattern(
            id=uuid4(),
            opportunity_id=opp_a.id,
            opportunity_type="freelance",
            total_score=Decimal("8.60"),
            outcome="positive",
            actual_value_thb=Decimal("25000"),
            lost_reason=None,
        ),
        OutcomePattern(
            id=uuid4(),
            opportunity_id=opp_b.id,
            opportunity_type="grant",
            total_score=Decimal("7.90"),
            outcome="negative",
            actual_value_thb=Decimal("0"),
            lost_reason="timing_bad",
        ),
        OutcomePattern(
            id=uuid4(),
            opportunity_id=opp_b.id,
            opportunity_type="grant",
            total_score=Decimal("7.20"),
            outcome="negative",
            actual_value_thb=Decimal("0"),
            lost_reason="timing_bad",
        ),
    ]
    db_session.add_all(patterns)
    await db_session.commit()

    auth = MCPAuthContext.system(organization_id=str(default_org.id))
    resp = await mcp_registry.call_tool(
        "get_outcome_patterns_summary",
        {"organization_id": str(default_org.id), "limit": 5},
        auth=auth,
    )

    assert resp.ok is True
    assert resp.data["total_patterns"] == 3
    assert resp.data["positive_count"] == 1
    assert resp.data["negative_count"] == 2
    assert resp.data["avg_actual_value_thb"] == "8333.333333333334"
    assert resp.data["top_lost_reasons"][0]["reason"] == "timing_bad"
    assert resp.data["top_lost_reasons"][0]["count"] == 2
    assert resp.data["recent_patterns"][0]["opportunity_title"] in {"Opportunity A", "Opportunity B"}
