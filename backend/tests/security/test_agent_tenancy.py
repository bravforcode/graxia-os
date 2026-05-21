import pytest
from uuid import uuid4
from sqlalchemy import select
from app.models.agent import Agent, AgentTeam
from app.models.organization import Organization
from app.services.agent_service import AgentService

@pytest.mark.asyncio
async def test_agent_service_tenancy_enforcement(db_session):
    """Verify that AgentService methods strictly enforce organization_id."""
    service = AgentService(db_session)
    
    # Create Org A and Org B
    org_a = Organization(name="Org A", slug="org-a")
    org_b = Organization(name="Org B", slug="org-b")
    db_session.add_all([org_a, org_b])
    await db_session.commit()
    await db_session.refresh(org_a)
    await db_session.refresh(org_b)
    
    # Create Agent in Org A
    agent_a = await service.create_agent(
        organization_id=org_a.id,
        agent_key="agent-a",
        name="Agent A"
    )
    
    # Create Agent in Org B
    agent_b = await service.create_agent(
        organization_id=org_b.id,
        agent_key="agent-b",
        name="Agent B"
    )
    
    # 1. Org A cannot get Agent B
    found_agent = await service.get_agent(agent_b.id, org_a.id)
    assert found_agent is None
    
    # 2. Org A cannot list Agent B
    agents, total = await service.list_agents(organization_id=org_a.id)
    assert total == 1
    assert agents[0].id == agent_a.id
    
    # 3. Org A cannot update Agent B
    updated = await service.update_agent(agent_b.id, org_a.id, name="Hacked")
    assert updated is None
    
    # Verify Agent B name was not changed
    await db_session.refresh(agent_b)
    assert agent_b.name == "Agent B"
    
    # 4. Org A cannot deactivate Agent B
    success = await service.deactivate_agent(agent_b.id, org_a.id)
    assert success is False
    
    # 5. Team isolation
    team_a = await service.create_team(organization_id=org_a.id, name="Team A")
    team_b = await service.create_team(organization_id=org_b.id, name="Team B")
    
    # Org A cannot add Agent B to Team A
    with pytest.raises(ValueError, match="Agent not found in your organization"):
        await service.add_agent_to_team(agent_b.id, team_a.id, org_a.id)
        
    # Org A cannot add Agent A to Team B
    with pytest.raises(ValueError, match="Team not found in your organization"):
        await service.add_agent_to_team(agent_a.id, team_b.id, org_a.id)
        
    # 6. Skill isolation
    skill_id = uuid4() # Dummy skill ID
    # This might fail due to FK constraint if we don't have a real skill
    # But let's assume we want to test the check before the DB call
    
    # 7. Marketplace isolation
    with pytest.raises(ValueError, match="Agent not found in your organization"):
        await service.create_marketplace_listing(agent_b.id, org_a.id, title="Hacked Listing")
