"""
Multi-Agent Orchestration Engine — Feature 40
Coordinates complex tasks across multiple agents with intelligent task distribution
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import (
    Agent,
    AgentCollaboration,
    AgentCollaborationMember,
    AgentCollaborationMessage,
    CollaborationStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class TaskRequirement:
    """Requirements for a task to be assigned to agents."""

    skill_ids: list[UUID] = field(default_factory=list)
    expertise_domains: list[str] = field(default_factory=list)
    min_proficiency: int = 5
    min_reputation: float = 50.0
    max_agents: int = 5
    requires_team: bool = False


@dataclass
class AgentAssignment:
    """Agent assigned to a task with role and responsibilities."""

    agent_id: UUID
    role: str
    responsibilities: list[str] = field(default_factory=list)
    assigned_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CollaborationPlan:
    """Execution plan for multi-agent collaboration."""

    collaboration_id: UUID
    orchestrator_id: UUID | None
    assignments: list[AgentAssignment] = field(default_factory=list)
    phases: list[dict[str, Any]] = field(default_factory=list)
    communication_protocol: str = "async"


class AgentOrchestrator:
    """
    Multi-Agent Orchestration Engine

    Features:
    - 40: Multi-Agent Orchestration
    - Intelligent agent selection based on skills and reputation
    - Task decomposition and distribution
    - Real-time collaboration coordination
    - Conflict resolution and consensus building
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._active_collaborations: dict[UUID, CollaborationPlan] = {}
        self._message_queues: dict[UUID, asyncio.Queue] = {}

    # ═════════════════════════════════════════════════════════════════════════
    # AGENT SELECTION & ASSIGNMENT
    # ═════════════════════════════════════════════════════════════════════════

    async def find_best_agents(
        self,
        requirements: TaskRequirement,
        exclude_agents: list[UUID] | None = None,
    ) -> list[Agent]:
        """
        Find the best agents for a task based on requirements.

        Uses weighted scoring:
        - Skill match: 40%
        - Proficiency level: 25%
        - Reputation score: 20%
        - Team collaboration history: 15%
        """

        exclude_agents = exclude_agents or []

        # Base query
        query = select(Agent).where(
            Agent.is_active,
            Agent.reputation_score >= requirements.min_reputation,
        )

        if exclude_agents:
            query = query.where(~Agent.id.in_(exclude_agents))

        # Filter by expertise domains
        if requirements.expertise_domains:
            # Use JSONB containment
            for domain in requirements.expertise_domains:
                query = query.where(Agent.expertise_domains.contains([domain]))

        result = await self.db.execute(query)
        candidates = list(result.scalars().all())

        # Score candidates
        scored_agents = []
        for agent in candidates:
            score = await self._score_agent_for_task(agent, requirements)
            scored_agents.append((agent, score))

        # Sort by score and return top agents
        scored_agents.sort(key=lambda x: x[1], reverse=True)

        return [agent for agent, _ in scored_agents[: requirements.max_agents]]

    async def _score_agent_for_task(
        self,
        agent: Agent,
        requirements: TaskRequirement,
    ) -> float:
        """Calculate fitness score for an agent on a task."""
        score = 0.0

        # Skill match (40%)
        if requirements.skill_ids:
            from app.models.agent import AgentSkill

            result = await self.db.execute(
                select(AgentSkill)
                .where(AgentSkill.agent_id == agent.id)
                .where(AgentSkill.skill_id.in_(requirements.skill_ids))
            )
            agent_skills = result.scalars().all()

            if agent_skills:
                # Calculate average proficiency for required skills
                avg_proficiency = sum(s.proficiency_level for s in agent_skills) / len(agent_skills)
                skill_match = len(agent_skills) / len(requirements.skill_ids)
                score += (skill_match * 0.4 + (avg_proficiency / 10) * 0.4) * 40

        # Reputation score (20%)
        score += (float(agent.reputation_score) / 100) * 20

        # Success rate (15%)
        if agent.total_tasks_completed > 0:
            score += float(agent.success_rate) * 0.15

        # Availability bonus (10%)
        if agent.status == "active":
            score += 10

        # Specialization match (15%)
        if requirements.expertise_domains and agent.specialization:
            if agent.specialization in requirements.expertise_domains:
                score += 15

        return score

    # ═════════════════════════════════════════════════════════════════════════
    # COLLABORATION SESSION MANAGEMENT
    # ═════════════════════════════════════════════════════════════════════════

    async def create_collaboration(
        self,
        title: str,
        task_description: str,
        task_type: str,
        agent_ids: list[UUID],
        orchestrator_id: UUID | None = None,
        parent_collaboration_id: UUID | None = None,
    ) -> AgentCollaboration:
        """Create a new multi-agent collaboration session."""
        # Generate session key
        session_key = f"COLLAB-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{str(uuid4())[:8]}"

        # Create collaboration record
        collaboration = AgentCollaboration(
            session_key=session_key,
            title=title,
            task_description=task_description,
            task_type=task_type,
            orchestrator_agent_id=orchestrator_id,
            parent_collaboration_id=parent_collaboration_id,
            status=CollaborationStatus.PENDING.value,
        )

        self.db.add(collaboration)
        await self.db.flush()  # Get the ID

        # Add agent members
        for i, agent_id in enumerate(agent_ids):
            role = "orchestrator" if agent_id == orchestrator_id else "contributor"
            if i == 0 and not orchestrator_id:
                role = "orchestrator"  # First agent becomes orchestrator if none specified

            member = AgentCollaborationMember(
                collaboration_id=collaboration.id,
                agent_id=agent_id,
                role=role,
            )
            self.db.add(member)

        await self.db.commit()
        await self.db.refresh(collaboration)

        # Initialize collaboration plan
        assignments = [
            AgentAssignment(agent_id=agent_id, role="contributor") for agent_id in agent_ids
        ]

        plan = CollaborationPlan(
            collaboration_id=collaboration.id,
            orchestrator_id=orchestrator_id or agent_ids[0] if agent_ids else None,
            assignments=assignments,
        )

        self._active_collaborations[collaboration.id] = plan
        self._message_queues[collaboration.id] = asyncio.Queue()

        logger.info(f"Created collaboration {session_key} with {len(agent_ids)} agents")

        return collaboration

    async def start_collaboration(self, collaboration_id: UUID) -> AgentCollaboration:
        """Start a collaboration session."""
        collaboration = await self.db.get(AgentCollaboration, collaboration_id)
        if not collaboration:
            raise ValueError(f"Collaboration {collaboration_id} not found")

        collaboration.status = CollaborationStatus.ACTIVE.value
        collaboration.started_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(collaboration)

        # Send start message to all agents
        await self.broadcast_message(
            collaboration_id=collaboration_id,
            message_type="system",
            content={
                "event": "collaboration_started",
                "timestamp": datetime.utcnow().isoformat(),
                "task": collaboration.task_description,
            },
        )

        logger.info(f"Started collaboration {collaboration.session_key}")
        return collaboration

    async def complete_collaboration(
        self,
        collaboration_id: UUID,
        result_summary: str,
        result_data: dict[str, Any] | None = None,
    ) -> AgentCollaboration:
        """Mark a collaboration as completed."""
        collaboration = await self.db.get(AgentCollaboration, collaboration_id)
        if not collaboration:
            raise ValueError(f"Collaboration {collaboration_id} not found")

        collaboration.status = CollaborationStatus.COMPLETED.value
        collaboration.completed_at = datetime.utcnow()
        collaboration.result_summary = result_summary
        collaboration.result_data = result_data or {}

        # Calculate duration
        if collaboration.started_at:
            collaboration.duration_ms = int(
                (collaboration.completed_at - collaboration.started_at).total_seconds() * 1000
            )

        await self.db.commit()
        await self.db.refresh(collaboration)

        # Cleanup
        if collaboration_id in self._active_collaborations:
            del self._active_collaborations[collaboration_id]
        if collaboration_id in self._message_queues:
            del self._message_queues[collaboration_id]

        logger.info(f"Completed collaboration {collaboration.session_key}")
        return collaboration

    # ═════════════════════════════════════════════════════════════════════════
    # COMMUNICATION & COORDINATION
    # ═════════════════════════════════════════════════════════════════════════

    async def send_message(
        self,
        collaboration_id: UUID,
        agent_id: UUID,
        message_type: str,
        content: dict[str, Any],
    ) -> AgentCollaborationMessage:
        """Send a message within a collaboration."""
        # Get member record
        from sqlalchemy import select

        result = await self.db.execute(
            select(AgentCollaborationMember)
            .where(AgentCollaborationMember.collaboration_id == collaboration_id)
            .where(AgentCollaborationMember.agent_id == agent_id)
        )
        member = result.scalar_one_or_none()

        if not member:
            raise ValueError(f"Agent {agent_id} is not a member of this collaboration")

        message = AgentCollaborationMessage(
            member_id=member.id,
            message_type=message_type,
            content=str(content),  # Store as string
            metadata=content,
        )

        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)

        # Add to queue for real-time delivery
        if collaboration_id in self._message_queues:
            await self._message_queues[collaboration_id].put(
                {
                    "type": message_type,
                    "agent_id": str(agent_id),
                    "content": content,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

        return message

    async def broadcast_message(
        self,
        collaboration_id: UUID,
        message_type: str,
        content: dict[str, Any],
        exclude_agent_id: UUID | None = None,
    ) -> None:
        """Broadcast a message to all agents in a collaboration."""
        from sqlalchemy import select

        # Get all members
        result = await self.db.execute(
            select(AgentCollaborationMember).where(
                AgentCollaborationMember.collaboration_id == collaboration_id
            )
        )
        members = result.scalars().all()

        # Send to each member
        for member in members:
            if exclude_agent_id and member.agent_id == exclude_agent_id:
                continue

            await self.send_message(
                collaboration_id=collaboration_id,
                agent_id=member.agent_id,
                message_type=message_type,
                content=content,
            )

    async def get_collaboration_messages(
        self,
        collaboration_id: UUID,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AgentCollaborationMessage]:
        """Get messages from a collaboration."""
        from sqlalchemy import select

        query = (
            select(AgentCollaborationMessage)
            .join(AgentCollaborationMember)
            .where(AgentCollaborationMember.collaboration_id == collaboration_id)
            .order_by(desc(AgentCollaborationMessage.created_at))
            .limit(limit)
        )

        if since:
            query = query.where(AgentCollaborationMessage.created_at > since)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ═════════════════════════════════════════════════════════════════════════
    # TASK DECOMPOSITION & DISTRIBUTION
    # ═════════════════════════════════════════════════════════════════════════

    async def decompose_task(
        self,
        task_description: str,
        complexity: str = "medium",
    ) -> list[dict[str, Any]]:
        """
        Decompose a complex task into subtasks.

        This is a simplified version. In production, this would use AI
        to intelligently break down tasks.
        """
        # Simplified decomposition based on complexity
        if complexity == "low":
            return [
                {
                    "id": f"subtask-{i}",
                    "description": f"Step {i + 1} of {task_description}",
                    "estimated_duration_ms": 60000,
                    "required_skills": [],
                    "dependencies": [],
                }
                for i in range(2)
            ]
        elif complexity == "medium":
            return [
                {
                    "id": f"subtask-{i}",
                    "description": f"Step {i + 1} of {task_description}",
                    "estimated_duration_ms": 120000,
                    "required_skills": [],
                    "dependencies": [f"subtask-{i - 1}"] if i > 0 else [],
                }
                for i in range(4)
            ]
        else:  # high
            return [
                {
                    "id": f"subtask-{i}",
                    "description": f"Step {i + 1} of {task_description}",
                    "estimated_duration_ms": 300000,
                    "required_skills": [],
                    "dependencies": [f"subtask-{i - 1}"] if i > 0 else [],
                }
                for i in range(8)
            ]

    async def assign_subtasks(
        self,
        collaboration_id: UUID,
        subtasks: list[dict[str, Any]],
    ) -> CollaborationPlan:
        """Assign subtasks to agents in a collaboration."""
        collaboration = self._active_collaborations.get(collaboration_id)
        if not collaboration:
            raise ValueError(f"Collaboration {collaboration_id} not found or not active")

        # Simple round-robin assignment for now
        assignments = collaboration.assignments
        for i, subtask in enumerate(subtasks):
            agent_assignment = assignments[i % len(assignments)]
            agent_assignment.responsibilities.append(subtask["id"])

        # Update phases
        collaboration.phases = [
            {
                "phase_id": f"phase-{i}",
                "subtasks": [st["id"] for st in subtasks[i : i + 2]],
                "status": "pending",
            }
            for i in range(0, len(subtasks), 2)
        ]

        logger.info(
            f"Assigned {len(subtasks)} subtasks to {len(assignments)} agents "
            f"in collaboration {collaboration_id}"
        )

        return collaboration

    # ═════════════════════════════════════════════════════════════════════════
    # CONSENSUS & CONFLICT RESOLUTION
    # ═════════════════════════════════════════════════════════════════════════

    async def request_consensus(
        self,
        collaboration_id: UUID,
        decision_topic: str,
        options: list[str],
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        """Request consensus from all agents on a decision."""
        # Send voting request
        await self.broadcast_message(
            collaboration_id=collaboration_id,
            message_type="consensus_request",
            content={
                "topic": decision_topic,
                "options": options,
                "timeout_seconds": timeout_seconds,
            },
        )

        # Wait for responses (simplified)
        # In production, this would collect actual votes
        return {
            "topic": decision_topic,
            "consensus_reached": True,
            "selected_option": options[0] if options else None,
            "votes": {option: 1 for option in options},
        }

    # ═════════════════════════════════════════════════════════════════════════
    # MONITORING & STATUS
    # ═════════════════════════════════════════════════════════════════════════

    async def get_collaboration_status(
        self,
        collaboration_id: UUID,
    ) -> dict[str, Any]:
        """Get current status of a collaboration."""
        collaboration = await self.db.get(AgentCollaboration, collaboration_id)
        if not collaboration:
            raise ValueError(f"Collaboration {collaboration_id} not found")

        # Get members
        from sqlalchemy import select

        result = await self.db.execute(
            select(AgentCollaborationMember).where(
                AgentCollaborationMember.collaboration_id == collaboration_id
            )
        )
        members = result.scalars().all()

        # Calculate progress
        plan = self._active_collaborations.get(collaboration_id)
        completed_phases = sum(
            1 for p in (plan.phases if plan else []) if p.get("status") == "completed"
        )
        total_phases = len(plan.phases) if plan else 1
        progress = (completed_phases / total_phases) * 100 if total_phases > 0 else 0

        return {
            "collaboration_id": collaboration_id,
            "session_key": collaboration.session_key,
            "status": collaboration.status,
            "title": collaboration.title,
            "progress_percentage": progress,
            "member_count": len(members),
            "members": [
                {
                    "agent_id": m.agent_id,
                    "role": m.role,
                    "tasks_completed": m.tasks_completed,
                }
                for m in members
            ],
            "started_at": collaboration.started_at,
            "completed_at": collaboration.completed_at,
        }

    async def get_active_collaborations(
        self,
        limit: int = 50,
    ) -> list[AgentCollaboration]:
        """Get all active collaboration sessions."""
        result = await self.db.execute(
            select(AgentCollaboration)
            .where(AgentCollaboration.status == CollaborationStatus.ACTIVE.value)
            .order_by(desc(AgentCollaboration.started_at))
            .limit(limit)
        )
        return list(result.scalars().all())


# Factory function for creating orchestrator instances
async def get_agent_orchestrator(db: AsyncSession) -> AgentOrchestrator:
    """Get or create an agent orchestrator instance."""
    return AgentOrchestrator(db)
