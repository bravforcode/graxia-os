# Design Spec: Agent Tenancy Enforcement (Task 1.1)

Date: 2026-05-06
Topic: Enforce strict tenancy in `backend/app/api/agents.py` and `backend/app/services/agent_service.py`.

## 1. Problem Statement
The current Agent Ecosystem API does not strictly enforce tenancy. Some endpoints allow access to agents across different organizations because they don't validate the `organization_id` of the requesting user against the resource being accessed.

## 2. Proposed Changes

### 2.1 API Layer (`backend/app/api/agents.py`)
- **Import Dependencies**:
  - `from app.middleware.tenant import get_org`
  - `from app.models.organization import Organization`
- **Inject Tenancy**: Add `org: Organization = Depends(get_org)` to every endpoint function signature.
- **Pass Context**: Pass `org.id` to every `AgentService` method call.
- **Audit Logging**: Add `logger.info(f"Tenant {org.id} [action] [resource_id]")` to every endpoint.
- **Response Validation**: Ensure all endpoints use existing Pydantic models for response serialization.

### 2.2 Service Layer (`backend/app/services/agent_service.py`)
- **Update Method Signatures**: Ensure ALL methods that interact with Agents, Teams, or related resources accept `organization_id: UUID`.
- **Enforce Tenancy in Queries**:
  - Update `get_agent`, `get_agent_by_key`, `list_agents`, `update_agent`, `deactivate_agent`, `create_team` to use `organization_id` in the `WHERE` clause.
  - For sub-resources (Skills, Marketplace, Mentorship, Wishlist, Certificates), ensure the parent Agent belongs to the provided `organization_id` before performing the operation.

### 2.3 Verification (`tests/security/test_isolation_0.py`)
- Create an integration test that:
  - Creates Org A and Org B.
  - Creates User A (Org A) and User B (Org B).
  - Verifies User A can create/list/get/update/delete agents in Org A.
  - Verifies User A CANNOT access agents created by User B in Org B (expect 404 or 403).

## 3. Implementation Details

Example Refactor for `get_agent`:
```python
@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: UUID,
    org: Organization = Depends(get_org),
    service: AgentService = Depends(get_agent_service),
):
    """Get agent details by ID."""
    agent = await service.get_agent(agent_id, org.id)
    if not agent:
        logger.warning(f"Tenant {org.id} attempted to access non-existent or unauthorized agent {agent_id}")
        raise HTTPException(status_code=404, detail="Agent not found")
    logger.info(f"Tenant {org.id} accessed agent {agent_id}")
    return agent
```

## 4. Risks & Mitigations
- **Broken Endpoints**: Changing service signatures might break other parts of the system if not all callers are updated. Mitigation: Grep for all `AgentService` usages.
- **Performance**: Adding `organization_id` to queries is indexed, so performance impact should be negligible.
