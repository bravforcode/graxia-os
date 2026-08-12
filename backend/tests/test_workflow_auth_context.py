from __future__ import annotations

import pytest
from uuid import UUID

from app.agent_workflows.errors import WorkflowOrgMismatchError, WorkflowPolicyViolationError
from app.agent_workflows.service import workflow_engine_service
from app.mcp.schemas import MCPAuthContext


TEST_ORG = "00000000-0000-0000-0000-000000000001"
OTHER_ORG = "00000000-0000-0000-0000-000000000002"


@pytest.mark.asyncio
async def test_workflow_run_denies_org_mismatch():
    auth = MCPAuthContext(
        organization_id=UUID(TEST_ORG),
        actor_type="user",
        actor_id="user-1",
        permissions=["workflow:run", "analytics:read"],
        is_authenticated=True,
    )

    with pytest.raises(WorkflowOrgMismatchError):
        await workflow_engine_service.run_workflow(
            workflow_type="daily_funnel_brief",
            organization_id=OTHER_ORG,
            inputs={},
            auth_ctx=auth,
        )


@pytest.mark.asyncio
async def test_workflow_run_requires_declared_permissions():
    auth = MCPAuthContext(
        organization_id=UUID(TEST_ORG),
        actor_type="user",
        actor_id="user-2",
        permissions=["workflow:run"],
        is_authenticated=True,
    )

    with pytest.raises(WorkflowPolicyViolationError):
        await workflow_engine_service.run_workflow(
            workflow_type="daily_funnel_brief",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
