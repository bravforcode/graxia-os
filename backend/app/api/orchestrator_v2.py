"""
Multi-Agent Orchestrator API — Feature 40
Advanced endpoints for agent collaboration and task orchestration
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_orchestrator import AgentOrchestrator, TaskRequirement, get_agent_orchestrator
from app.database import get_db

router = APIRouter(prefix="/orchestrator", tags=["Multi-Agent Orchestration"])


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════


class CollaborationCreate(BaseModel):
    title: str
    task_description: str
    task_type: str
    agent_ids: list[UUID] = Field(default_factory=list)
    orchestrator_id: UUID | None = None
    parent_collaboration_id: UUID | None = None
    auto_assign: bool = True
    required_skills: list[UUID] = Field(default_factory=list)
    expertise_domains: list[str] = Field(default_factory=list)
    max_agents: int = Field(default=5, ge=1, le=20)


class CollaborationOut(BaseModel):
    id: UUID
    session_key: str
    title: str
    task_type: str
    status: str
    progress_percentage: float
    member_count: int
    started_at: str | None
    created_at: str


class TaskDecomposeRequest(BaseModel):
    task_description: str
    complexity: str = "medium"  # low, medium, high


class SubtaskOut(BaseModel):
    id: str
    description: str
    estimated_duration_ms: int
    required_skills: list[UUID]
    dependencies: list[str]


class MessageSend(BaseModel):
    agent_id: UUID
    message_type: str = "text"
    content: dict[str, Any] = Field(default_factory=dict)


class MessageBroadcast(BaseModel):
    message_type: str = "system"
    content: dict[str, Any] = Field(default_factory=dict)


class ConsensusRequest(BaseModel):
    decision_topic: str
    options: list[str]
    timeout_seconds: int = Field(default=60, ge=10, le=300)


# ═══════════════════════════════════════════════════════════════════════════════
# DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════════════


async def get_orchestrator(db: AsyncSession = Depends(get_db)) -> AgentOrchestrator:
    return await get_agent_orchestrator(db)


# ═══════════════════════════════════════════════════════════════════════════════
# COLLABORATION MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/collaborations", response_model=CollaborationOut)
async def create_collaboration(
    data: CollaborationCreate,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """
    Create a new multi-agent collaboration session.

    If auto_assign is True and agent_ids is empty, agents will be
    automatically selected based on required_skills and expertise_domains.
    """
    try:
        # Auto-assign agents if needed
        agent_ids = data.agent_ids
        if data.auto_assign and not agent_ids:
            requirements = TaskRequirement(
                skill_ids=data.required_skills,
                expertise_domains=data.expertise_domains,
                max_agents=data.max_agents,
            )
            agents = await orchestrator.find_best_agents(requirements)
            agent_ids = [agent.id for agent in agents]

        if not agent_ids:
            raise HTTPException(status_code=400, detail="No agents available for collaboration")

        # Create collaboration
        collaboration = await orchestrator.create_collaboration(
            title=data.title,
            task_description=data.task_description,
            task_type=data.task_type,
            agent_ids=agent_ids,
            orchestrator_id=data.orchestrator_id,
            parent_collaboration_id=data.parent_collaboration_id,
        )

        return {
            "id": collaboration.id,
            "session_key": collaboration.session_key,
            "title": collaboration.title,
            "task_type": collaboration.task_type,
            "status": collaboration.status,
            "progress_percentage": 0.0,
            "member_count": len(agent_ids),
            "started_at": collaboration.started_at,
            "created_at": collaboration.created_at,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/collaborations/{collaboration_id}/start")
async def start_collaboration(
    collaboration_id: UUID,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """Start a collaboration session."""
    try:
        collaboration = await orchestrator.start_collaboration(collaboration_id)
        return {
            "message": "Collaboration started",
            "collaboration_id": collaboration_id,
            "status": collaboration.status,
            "started_at": collaboration.started_at,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/collaborations/{collaboration_id}/complete")
async def complete_collaboration(
    collaboration_id: UUID,
    result_summary: str,
    result_data: dict[str, Any] | None = None,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """Mark a collaboration as completed."""
    try:
        collaboration = await orchestrator.complete_collaboration(
            collaboration_id=collaboration_id,
            result_summary=result_summary,
            result_data=result_data,
        )
        return {
            "message": "Collaboration completed",
            "collaboration_id": collaboration_id,
            "status": collaboration.status,
            "completed_at": collaboration.completed_at,
            "duration_ms": collaboration.duration_ms,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/collaborations/{collaboration_id}/status")
async def get_collaboration_status(
    collaboration_id: UUID,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """Get real-time status of a collaboration."""
    try:
        status = await orchestrator.get_collaboration_status(collaboration_id)
        return status
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/collaborations/active")
async def get_active_collaborations(
    limit: int = Query(50, ge=1, le=100),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """Get all active collaboration sessions."""
    collaborations = await orchestrator.get_active_collaborations(limit)
    return {
        "collaborations": [
            {
                "id": c.id,
                "session_key": c.session_key,
                "title": c.title,
                "task_type": c.task_type,
                "status": c.status,
                "started_at": c.started_at,
            }
            for c in collaborations
        ],
        "total": len(collaborations),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TASK DECOMPOSITION & ASSIGNMENT
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/tasks/decompose")
async def decompose_task(
    data: TaskDecomposeRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """
    Decompose a complex task into manageable subtasks.

    Complexity levels:
    - low: 2 subtasks, 1 min each
    - medium: 4 subtasks, 2 min each
    - high: 8 subtasks, 5 min each
    """
    try:
        subtasks = await orchestrator.decompose_task(
            task_description=data.task_description,
            complexity=data.complexity,
        )
        return {
            "task_description": data.task_description,
            "complexity": data.complexity,
            "subtasks": subtasks,
            "total_subtasks": len(subtasks),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/collaborations/{collaboration_id}/assign")
async def assign_subtasks(
    collaboration_id: UUID,
    subtasks: list[SubtaskOut],
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """Assign subtasks to agents in a collaboration."""
    try:
        plan = await orchestrator.assign_subtasks(
            collaboration_id=collaboration_id,
            subtasks=[st.model_dump() for st in subtasks],
        )
        return {
            "collaboration_id": collaboration_id,
            "assignments": [
                {
                    "agent_id": a.agent_id,
                    "role": a.role,
                    "responsibilities": a.responsibilities,
                }
                for a in plan.assignments
            ],
            "phases": plan.phases,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT SELECTION
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/agents/select")
async def select_best_agents(
    required_skills: list[UUID] = Query(default_factory=list),
    expertise_domains: list[str] = Query(default_factory=list),
    min_proficiency: int = Query(5, ge=1, le=10),
    min_reputation: float = Query(50.0, ge=0, le=100),
    max_agents: int = Query(5, ge=1, le=20),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """
    Find the best agents for a task based on requirements.

    Agents are scored based on:
    - Skill match (40%)
    - Proficiency level (25%)
    - Reputation score (20%)
    - Collaboration history (15%)
    """
    try:
        requirements = TaskRequirement(
            skill_ids=required_skills,
            expertise_domains=expertise_domains,
            min_proficiency=min_proficiency,
            min_reputation=min_reputation,
            max_agents=max_agents,
        )

        agents = await orchestrator.find_best_agents(requirements)

        return {
            "requirements": {
                "required_skills": required_skills,
                "expertise_domains": expertise_domains,
                "min_proficiency": min_proficiency,
                "min_reputation": min_reputation,
            },
            "agents": [
                {
                    "id": agent.id,
                    "agent_key": agent.agent_key,
                    "name": agent.name,
                    "specialization": agent.specialization,
                    "reputation_score": float(agent.reputation_score),
                    "success_rate": float(agent.success_rate),
                }
                for agent in agents
            ],
            "total_found": len(agents),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# COMMUNICATION
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/collaborations/{collaboration_id}/messages")
async def send_message(
    collaboration_id: UUID,
    data: MessageSend,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """Send a message from an agent within a collaboration."""
    try:
        message = await orchestrator.send_message(
            collaboration_id=collaboration_id,
            agent_id=data.agent_id,
            message_type=data.message_type,
            content=data.content,
        )
        return {
            "message_id": message.id,
            "collaboration_id": collaboration_id,
            "agent_id": data.agent_id,
            "message_type": data.message_type,
            "created_at": message.created_at,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/collaborations/{collaboration_id}/broadcast")
async def broadcast_message(
    collaboration_id: UUID,
    data: MessageBroadcast,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """Broadcast a message to all agents in a collaboration."""
    try:
        await orchestrator.broadcast_message(
            collaboration_id=collaboration_id,
            message_type=data.message_type,
            content=data.content,
        )
        return {
            "message": "Broadcast sent successfully",
            "collaboration_id": collaboration_id,
            "message_type": data.message_type,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/collaborations/{collaboration_id}/messages")
async def get_messages(
    collaboration_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    since: str | None = None,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """Get messages from a collaboration."""
    from datetime import datetime

    since_dt = None
    if since:
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))

    try:
        messages = await orchestrator.get_collaboration_messages(
            collaboration_id=collaboration_id,
            since=since_dt,
            limit=limit,
        )
        return {
            "collaboration_id": collaboration_id,
            "messages": [
                {
                    "id": m.id,
                    "message_type": m.message_type,
                    "content": m.metadata,
                    "created_at": m.created_at,
                }
                for m in messages
            ],
            "total": len(messages),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# CONSENSUS & DECISION MAKING
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/collaborations/{collaboration_id}/consensus")
async def request_consensus(
    collaboration_id: UUID,
    data: ConsensusRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """Request consensus from all agents on a decision."""
    try:
        result = await orchestrator.request_consensus(
            collaboration_id=collaboration_id,
            decision_topic=data.decision_topic,
            options=data.options,
            timeout_seconds=data.timeout_seconds,
        )
        return {
            "collaboration_id": collaboration_id,
            "topic": result["topic"],
            "consensus_reached": result["consensus_reached"],
            "selected_option": result["selected_option"],
            "votes": result["votes"],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# REAL-TIME STREAMING (WebSocket would be implemented separately)
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/collaborations/{collaboration_id}/stream")
async def get_stream_info(
    collaboration_id: UUID,
):
    """Get WebSocket stream endpoint for real-time collaboration updates."""
    return {
        "collaboration_id": collaboration_id,
        "stream_endpoint": f"/ws/orchestrator/collaborations/{collaboration_id}/stream",
        "message": "Connect to WebSocket for real-time updates",
        "supported_events": [
            "message_received",
            "task_completed",
            "agent_joined",
            "agent_left",
            "consensus_reached",
            "phase_completed",
        ],
    }
