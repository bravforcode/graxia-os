"""Phase 16 route protection regression tests."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_approval_batch_resolve_is_org_scoped(async_client, db_session):
    from app.models.approval_request import ApprovalRequest
    from app.models.organization import Organization

    org_a = uuid4()
    org_b = uuid4()

    for org_id, name in ((org_a, "Org A"), (org_b, "Org B")):
        db_session.add(
            Organization(
                id=org_id,
                name=f"{name} {org_id}",
                slug=f"org-{org_id}",
                status="active",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
    await db_session.commit()

    approval = ApprovalRequest(
        id=uuid4(),
        organization_id=org_a,
        title="Batch approval",
        action_type="test",
        status="pending",
        policy_class="test",
        requested_by="test",
        batch_key="phase16-batch",
    )
    db_session.add(approval)
    await db_session.commit()

    wrong_org_resp = await async_client.patch(
        "/api/v1/approvals/batch/phase16-batch/approve",
        headers={"X-Graxia-Org-Id": str(org_b)},
    )
    assert wrong_org_resp.status_code == 200
    assert wrong_org_resp.json()["count"] == 0

    correct_org_resp = await async_client.patch(
        "/api/v1/approvals/batch/phase16-batch/approve",
        headers={"X-Graxia-Org-Id": str(org_a)},
    )
    assert correct_org_resp.status_code == 200
    assert correct_org_resp.json()["count"] == 1


@pytest.mark.asyncio
async def test_mcp_http_route_blocks_org_mismatch(async_client, default_org):
    other_org = uuid4()
    resp = await async_client.post(
        "/api/v1/mcp/tools/call",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_system_status",
                "organization_id": str(other_org),
                "arguments": {},
            },
        },
        headers={"X-Graxia-Org-Id": str(default_org.id)},
    )
    assert resp.status_code == 404
