"""
Agent Ecosystem Tenancy Isolation Tests
Verifies that agents and related resources are isolated between organizations.
"""
from uuid import uuid4
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.organization import Organization
from app.models.user import User
from app.core.auth import create_access_token

@pytest.fixture
async def two_orgs_with_users(db_session: AsyncSession):
    """Fixture to create two organizations and one user for each."""
    org_a = Organization(
        id=uuid4(),
        name="Org A",
        slug="org-a",
        plan="pro",
        status="active",
    )
    org_b = Organization(
        id=uuid4(),
        name="Org B",
        slug="org-b",
        plan="pro",
        status="active",
    )
    db_session.add_all([org_a, org_b])
    await db_session.flush()

    user_a = User(
        id=uuid4(),
        email=f"user-a-{uuid4().hex[:8]}@example.com",
        hashed_password="...",
        organization_id=org_a.id,
        role="admin",
        is_active=True,
    )
    user_b = User(
        id=uuid4(),
        email=f"user-b-{uuid4().hex[:8]}@example.com",
        hashed_password="...",
        organization_id=org_b.id,
        role="admin",
        is_active=True,
    )
    db_session.add_all([user_a, user_b])
    await db_session.commit()
    
    return {
        "org_a": org_a,
        "user_a": user_a,
        "token_a": create_access_token({"sub": str(user_a.id)}),
        "org_b": org_b,
        "user_b": user_b,
        "token_b": create_access_token({"sub": str(user_b.id)}),
    }

@pytest.mark.asyncio
async def test_agent_isolation(async_client: AsyncClient, two_orgs_with_users):
    """User A should not see User B's agents."""
    data = two_orgs_with_users
    
    # 1. User A creates an agent
    resp_a = await async_client.post(
        "/api/v1/agents",
        json={
            "agent_key": "agent-a",
            "name": "Agent A",
        },
        headers={"Authorization": f"Bearer {data['token_a']}"}
    )
    if resp_a.status_code != 201 and resp_a.status_code != 200:
        print(f"Error Response: {resp_a.text}")
    assert resp_a.status_code == 201 or resp_a.status_code == 200
    agent_a_id = resp_a.json()["id"]

    # 2. User B creates an agent
    resp_b = await async_client.post(
        "/api/v1/agents",
        json={
            "agent_key": "agent-b",
            "name": "Agent B",
        },
        headers={"Authorization": f"Bearer {data['token_b']}"}
    )
    assert resp_b.status_code == 201 or resp_b.status_code == 200
    agent_b_id = resp_b.json()["id"]

    # 3. User A lists agents - should only see Agent A
    list_resp = await async_client.get(
        "/api/v1/agents",
        headers={"Authorization": f"Bearer {data['token_a']}"}
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    ids = [item["id"] for item in items]
    assert agent_a_id in ids
    assert agent_b_id not in ids

    # 4. User A tries to GET Agent B - should be 404
    get_resp = await async_client.get(
        f"/api/v1/agents/{agent_b_id}",
        headers={"Authorization": f"Bearer {data['token_a']}"}
    )
    assert get_resp.status_code == 404
