"""
Agent Ecosystem API — Features 26-40
50+ endpoints for agents, teams, marketplace, mentorship
"""

import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.middleware.tenant import get_org
from app.models.organization import Organization
from app.services.agent_service import AgentService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["Agent Ecosystem"])


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════


class AgentCreate(BaseModel):
    agent_key: str
    name: str
    description: str | None = None
    specialization: str | None = None
    expertise_domains: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    specialization: str | None = None
    expertise_domains: list[str] | None = None
    config: dict[str, Any] | None = None


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_key: str
    name: str
    description: str | None
    status: str
    specialization: str | None
    expertise_domains: list[str]
    reputation_score: float
    total_tasks_completed: int
    success_rate: float
    created_at: Any


class AgentList(BaseModel):
    items: list[AgentOut]
    total: int
    page: int
    limit: int


class TeamCreate(BaseModel):
    name: str
    description: str | None = None
    team_type: str = "squad"
    max_members: int = 10
    is_public: bool = False


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    team_type: str
    max_members: int
    is_public: bool
    collective_score: float
    tasks_completed: int
    created_at: Any


class MarketplaceListingCreate(BaseModel):
    title: str
    description: str | None = None
    listing_type: str = "skill"
    price: float | None = None
    offered_skills: list[UUID] = Field(default_factory=list)
    requirements: str | None = None
    deliverables: str | None = None


class MarketplaceListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    title: str
    description: str | None
    listing_type: str
    price: float | None
    status: str
    views_count: int
    inquiries_count: int
    created_at: Any


class MentorshipCreate(BaseModel):
    mentor_id: UUID
    mentee_id: UUID
    focus_skills: list[UUID] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)


class WishlistAdd(BaseModel):
    skill_id: UUID
    priority: int = Field(default=5, ge=1, le=10)
    reason: str | None = None
    use_case: str | None = None


class CertificateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    skill_id: UUID
    certificate_key: str
    title: str
    proficiency_level_achieved: int
    score_achieved: float
    issued_by: str
    issued_at: Any
    expires_at: Any | None


class AgentTaskRequest(BaseModel):
    agent_name: str
    task: str
    context: dict[str, Any] | None = None


class AgentTaskResponse(BaseModel):
    success: bool
    result: str | None = None
    error: str | None = None


class AgentIdentityResponse(BaseModel):
    agent_id: str
    agent_name: str
    agent_type: str
    bio: str
    avatar_url: str | None = None
    reputation_score: float
    completed_tasks: int
    success_rate: float
    is_available: bool
    accounts: list[str]
    capabilities: list[dict[str, Any]]


class CreateAgentRequest(BaseModel):
    name: str
    agent_type: str
    bio: str = ""
    capabilities: list[dict[str, Any]] = Field(default_factory=list)


class NegotiationRequest(BaseModel):
    target_agent: str
    task: str
    terms: dict[str, Any] = Field(default_factory=dict)
    timeout_minutes: int = 10


class NegotiationResponse(BaseModel):
    negotiation_id: str
    status: str
    message: str


class AgentCommunicationRequest(BaseModel):
    target_agent: str | None = None  # None = broadcast
    topic: str
    content: dict[str, Any]
    message_type: str = "broadcast"


# ═══════════════════════════════════════════════════════════════════════════════
# DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════════════


async def get_agent_service(db: AsyncSession = Depends(get_db)) -> AgentService:
    return AgentService(db)


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT CRUD ENDPOINTS (Feature 26)
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("", response_model=AgentOut)
async def create_agent(
    data: AgentCreate,
    org: Organization = Depends(get_org),
    service: AgentService = Depends(get_agent_service),
):
    """Register a new agent in the ecosystem."""
    try:
        agent = await service.create_agent(
            organization_id=org.id,
            agent_key=data.agent_key,
            name=data.name,
            description=data.description,
            specialization=data.specialization,
            expertise_domains=data.expertise_domains,
            config=data.config,
        )
        logger.info(f"Tenant {org.id} created agent {agent.id}")
        return agent
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=AgentList)
async def list_agents(
    status: str | None = None,
    specialization: str | None = None,
    min_reputation: float | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    org: Organization = Depends(get_org),
    service: AgentService = Depends(get_agent_service),
):
    """List all agents with filtering."""
    agents, total = await service.list_agents(
        organization_id=org.id,
        status=status,
        specialization=specialization,
        min_reputation=min_reputation,
        limit=limit,
        offset=offset,
    )
    logger.info(f"Tenant {org.id} listed agents (total={total})")
    return AgentList(
        items=agents,
        total=total,
        page=(offset // limit) + 1,
        limit=limit,
    )


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: UUID,
    org: Organization = Depends(get_org),
    service: AgentService = Depends(get_agent_service),
):
    """Get agent details by ID."""
    agent = await service.get_agent(agent_id, org.id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    logger.info(f"Tenant {org.id} accessed agent {agent_id}")
    return agent


@router.put("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: UUID,
    data: AgentUpdate,
    org: Organization = Depends(get_org),
    service: AgentService = Depends(get_agent_service),
):
    """Update agent details."""
    agent = await service.update_agent(
        agent_id=agent_id,
        organization_id=org.id,
        **data.model_dump(exclude_unset=True),
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    logger.info(f"Tenant {org.id} updated agent {agent_id}")
    return agent


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: UUID,
    org: Organization = Depends(get_org),
    service: AgentService = Depends(get_agent_service),
):
    """Deactivate an agent."""
    success = await service.deactivate_agent(agent_id, org.id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    logger.info(f"Tenant {org.id} deactivated agent {agent_id}")
    return {"message": "Agent deactivated successfully"}


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT SKILLS ENDPOINTS (Features 36, 38)
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{agent_id}/skills")
async def assign_skill_to_agent(
    agent_id: UUID,
    skill_id: UUID,
    proficiency_level: int = Query(1, ge=1, le=10),
    is_favorite: bool = False,
    org: Organization = Depends(get_org),
    service: AgentService = Depends(get_agent_service),
):
    """Assign a skill to an agent."""
    # Verify agent belongs to org
    agent = await service.get_agent(agent_id, org.id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    try:
        agent_skill = await service.assign_skill_to_agent(
            agent_id=agent_id,
            skill_id=skill_id,
            organization_id=org.id,
            proficiency_level=proficiency_level,
            is_favorite=is_favorite,
        )
        logger.info(f"Tenant {org.id} assigned skill {skill_id} to agent {agent_id}")
        return {
            "id": agent_skill.id,
            "agent_id": agent_skill.agent_id,
            "skill_id": agent_skill.skill_id,
            "proficiency_level": agent_skill.proficiency_level,
            "created_at": agent_skill.created_at,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{agent_id}/skills")
async def get_agent_skills(
    agent_id: UUID,
    min_proficiency: int | None = Query(None, ge=1, le=10),
    org: Organization = Depends(get_org),
    service: AgentService = Depends(get_agent_service),
):
    """Get all skills assigned to an agent."""
    # Verify agent belongs to org
    agent = await service.get_agent(agent_id, org.id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    skills = await service.get_agent_skills(agent_id, org.id, min_proficiency)
    logger.info(f"Tenant {org.id} listed skills for agent {agent_id}")
    return {
        "agent_id": agent_id,
        "skills": [
            {
                "id": s.id,
                "skill_id": s.skill_id,
                "proficiency_level": s.proficiency_level,
                "mastery_percentage": float(s.mastery_percentage),
                "usage_count": s.usage_count,
                "is_favorite": s.is_favorite,
                "last_used_at": s.last_used_at,
            }
            for s in skills
        ],
        "total": len(skills),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT TEAMS ENDPOINTS (Feature 34)
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/teams", response_model=TeamOut)
async def create_team(
    data: TeamCreate,
    org: Organization = Depends(get_org),
    service: AgentService = Depends(get_agent_service),
):
    """Create a new agent team."""
    team = await service.create_team(
        organization_id=org.id,
        name=data.name,
        description=data.description,
        team_type=data.team_type,
        max_members=data.max_members,
        is_public=data.is_public,
    )
    logger.info(f"Tenant {org.id} created team {team.id}")
    return team


@router.get("/teams/{team_id}")
async def get_team(
    team_id: UUID,
    org: Organization = Depends(get_org),
    service: AgentService = Depends(get_agent_service),
):
    """Get team details with members."""
    # Simplified lookup with tenancy
    from app.models.agent import AgentTeam
    result = await service.db.execute(
        select(AgentTeam).where(AgentTeam.id == team_id, AgentTeam.organization_id == org.id)
    )
    team = result.scalar_one_or_none()
    
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
        
    members = await service.get_team_members(team_id, org.id)
    logger.info(f"Tenant {org.id} accessed team {team_id}")
    return {
        "team": team,
        "members": members,
        "member_count": len(members),
    }
