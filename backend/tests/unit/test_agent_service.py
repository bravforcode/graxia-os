"""
Unit tests for AgentService
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.models.agent import Agent, AgentTeam
from app.services.agent_service import AgentService
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_db():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def agent_service(mock_db):
    return AgentService(mock_db)


@pytest.mark.asyncio
async def test_create_agent(agent_service, mock_db):
    org_id = uuid4()
    agent_key = "test_agent"
    name = "Test Agent"

    # Mock db.refresh to set an ID
    async def mock_refresh(obj):
        obj.id = uuid4()

    mock_db.refresh.side_effect = mock_refresh

    agent = await agent_service.create_agent(
        organization_id=org_id,
        agent_key=agent_key,
        name=name,
        specialization="testing",
    )

    assert agent.agent_key == agent_key
    assert agent.name == name
    assert agent.organization_id == org_id
    assert agent.specialization == "testing"
    assert agent.reputation_score == Decimal("50.00")
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_agent(agent_service, mock_db):
    agent_id = uuid4()
    org_id = uuid4()
    mock_agent = Agent(id=agent_id, organization_id=org_id, name="Test")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_agent
    mock_db.execute.return_value = mock_result

    agent = await agent_service.get_agent(agent_id, org_id)

    assert agent == mock_agent
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_update_reputation(agent_service, mock_db):
    agent_id = uuid4()
    org_id = uuid4()
    mock_agent = Agent(id=agent_id, organization_id=org_id, reputation_score=Decimal("50.00"), agent_key="test")

    # Mock get_agent (called internally by update_reputation)
    agent_service.get_agent = AsyncMock(return_value=mock_agent)

    updated_agent = await agent_service.update_reputation(
        agent_id=agent_id,
        organization_id=org_id,
        change_amount=5.5,
        reason_type="task_completion",
        description="Great job",
    )

    assert updated_agent.reputation_score == Decimal("55.50")
    mock_db.add.assert_called_once()  # Should add the ReputationLog
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_add_agent_to_team_capacity_full(agent_service, mock_db):
    agent_id = uuid4()
    team_id = uuid4()
    org_id = uuid4()
    
    # Mock get_agent and get_team (via database execute because I updated the implementation)
    mock_agent = Agent(id=agent_id, organization_id=org_id)
    mock_team = AgentTeam(id=team_id, organization_id=org_id, max_members=2)
    
    # Mock multiple calls to execute
    async def mock_execute(query, *args, **kwargs):
        mock_result = MagicMock()
        # Very simplified mock matching the logic flow in add_agent_to_team
        if "agents" in str(query):
            mock_result.scalar_one_or_none.return_value = mock_agent
        elif "agent_teams" in str(query):
            mock_result.scalar_one_or_none.return_value = mock_team
        elif "agent_team_members" in str(query):
            mock_result.scalar_one_or_none.return_value = None
        return mock_result
        
    mock_db.execute.side_effect = mock_execute
    
    # Mock current members count = 2
    mock_db.scalar.return_value = 2

    with pytest.raises(ValueError, match="Team is at maximum capacity"):
        await agent_service.add_agent_to_team(agent_id, team_id, org_id)
