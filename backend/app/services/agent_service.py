"""
Agent Ecosystem Service — Features 26-40
Core service for managing agents, teams, reputation, and marketplace
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import (
    Agent,
    AgentCertificate,
    AgentMarketplaceListing,
    AgentMentorship,
    AgentReputationLog,
    AgentSkill,
    AgentTeam,
    AgentTeamMember,
    AgentWishlist,
    MentorshipStatus,
)

logger = logging.getLogger(__name__)


class AgentService:
    """
    Agent Ecosystem Service

    Manages:
    - Agent registration and lifecycle (Feature 26)
    - Team management (Feature 34)
    - Reputation system (Feature 35)
    - Marketplace (Feature 26, 33)
    - Mentorship (Feature 29)
    - Wishlist (Feature 37)
    - Certificates (Feature 32)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ═════════════════════════════════════════════════════════════════════════
    # AGENT CRUD (Feature 26)
    # ═════════════════════════════════════════════════════════════════════════

    async def create_agent(
        self,
        organization_id: UUID,
        agent_key: str,
        name: str,
        description: str | None = None,
        specialization: str | None = None,
        expertise_domains: list[str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> Agent:
        """Register a new agent in the ecosystem."""
        agent = Agent(
            organization_id=organization_id,
            agent_key=agent_key,
            name=name,
            description=description,
            specialization=specialization,
            expertise_domains=expertise_domains or [],
            config=config or {},
            reputation_score=Decimal("50.00"),  # Start with neutral score
        )

        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)

        logger.info(f"Created agent: {agent_key} ({name}) for org {organization_id}")
        return agent

    async def get_agent(self, agent_id: UUID, organization_id: UUID) -> Agent | None:
        """Get agent by ID for a specific organization."""
        result = await self.db.execute(
            select(Agent).where(and_(Agent.id == agent_id, Agent.organization_id == organization_id))
        )
        return result.scalar_one_or_none()

    async def get_agent_by_key(self, agent_key: str, organization_id: UUID) -> Agent | None:
        """Get agent by unique key for a specific organization."""
        result = await self.db.execute(
            select(Agent).where(
                and_(Agent.agent_key == agent_key, Agent.organization_id == organization_id)
            )
        )
        return result.scalar_one_or_none()

    async def list_agents(
        self,
        organization_id: UUID,
        status: str | None = None,
        specialization: str | None = None,
        min_reputation: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Agent], int]:
        """List agents with filters for a specific organization."""
        query = select(Agent).where(Agent.organization_id == organization_id)

        if status:
            query = query.where(Agent.status == status)
        if specialization:
            query = query.where(Agent.specialization == specialization)
        if min_reputation:
            query = query.where(Agent.reputation_score >= min_reputation)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)

        # Get paginated results
        query = query.order_by(desc(Agent.reputation_score)).offset(offset).limit(limit)
        result = await self.db.execute(query)
        agents = result.scalars().all()

        return list(agents), total or 0

    async def update_agent(
        self,
        agent_id: UUID,
        organization_id: UUID,
        **updates: Any,
    ) -> Agent | None:
        """Update agent properties."""
        agent = await self.get_agent(agent_id, organization_id)
        if not agent:
            return None

        for key, value in updates.items():
            if hasattr(agent, key):
                setattr(agent, key, value)

        agent.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(agent)

        logger.info(f"Updated agent: {agent.agent_key} for org {organization_id}")
        return agent

    async def deactivate_agent(self, agent_id: UUID, organization_id: UUID) -> bool:
        """Deactivate an agent (soft delete)."""
        agent = await self.get_agent(agent_id, organization_id)
        if not agent:
            return False

        agent.status = "retired"
        agent.is_active = False
        await self.db.commit()

        logger.info(f"Deactivated agent: {agent.agent_key} for org {organization_id}")
        return True

    # ═════════════════════════════════════════════════════════════════════════
    # AGENT TEAMS (Feature 34)
    # ═════════════════════════════════════════════════════════════════════════

    async def create_team(
        self,
        organization_id: UUID,
        name: str,
        description: str | None = None,
        team_type: str = "squad",
        max_members: int = 10,
        is_public: bool = False,
    ) -> AgentTeam:
        """Create a new agent team."""
        team = AgentTeam(
            organization_id=organization_id,
            name=name,
            description=description,
            team_type=team_type,
            max_members=max_members,
            is_public=is_public,
        )

        self.db.add(team)
        await self.db.commit()
        await self.db.refresh(team)

        logger.info(f"Created team: {name} ({team_type}) for org {organization_id}")
        return team

    async def add_agent_to_team(
        self,
        agent_id: UUID,
        team_id: UUID,
        role: str = "member",
    ) -> AgentTeamMember:
        """Add an agent to a team."""
        # Check if already a member
        existing = await self.db.execute(
            select(AgentTeamMember).where(
                and_(
                    AgentTeamMember.agent_id == agent_id,
                    AgentTeamMember.team_id == team_id,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Agent is already a member of this team")

        # Check team capacity
        team = await self.db.get(AgentTeam, team_id)
        if not team:
            raise ValueError("Team not found")

        current_members = await self.db.scalar(
            select(func.count()).where(AgentTeamMember.team_id == team_id)
        )
        if current_members >= team.max_members:
            raise ValueError("Team is at maximum capacity")

        membership = AgentTeamMember(
            agent_id=agent_id,
            team_id=team_id,
            role=role,
        )

        self.db.add(membership)
        await self.db.commit()
        await self.db.refresh(membership)

        logger.info(f"Added agent {agent_id} to team {team_id} as {role}")
        return membership

    async def remove_agent_from_team(
        self,
        agent_id: UUID,
        team_id: UUID,
    ) -> bool:
        """Remove an agent from a team."""
        result = await self.db.execute(
            select(AgentTeamMember).where(
                and_(
                    AgentTeamMember.agent_id == agent_id,
                    AgentTeamMember.team_id == team_id,
                )
            )
        )
        membership = result.scalar_one_or_none()

        if not membership:
            return False

        await self.db.delete(membership)
        await self.db.commit()

        logger.info(f"Removed agent {agent_id} from team {team_id}")
        return True

    async def get_team_members(self, team_id: UUID) -> list[Agent]:
        """Get all agents in a team."""
        result = await self.db.execute(
            select(Agent).join(AgentTeamMember).where(AgentTeamMember.team_id == team_id)
        )
        return list(result.scalars().all())

    # ═════════════════════════════════════════════════════════════════════════
    # AGENT SKILLS (Features 36, 38)
    # ═════════════════════════════════════════════════════════════════════════

    async def assign_skill_to_agent(
        self,
        agent_id: UUID,
        skill_id: UUID,
        proficiency_level: int = 1,
        is_favorite: bool = False,
    ) -> AgentSkill:
        """Assign a skill to an agent."""
        # Check if already assigned
        existing = await self.db.execute(
            select(AgentSkill).where(
                and_(
                    AgentSkill.agent_id == agent_id,
                    AgentSkill.skill_id == skill_id,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Skill is already assigned to this agent")

        agent_skill = AgentSkill(
            agent_id=agent_id,
            skill_id=skill_id,
            proficiency_level=proficiency_level,
            is_favorite=is_favorite,
            learning_started_at=datetime.utcnow(),
        )

        self.db.add(agent_skill)
        await self.db.commit()
        await self.db.refresh(agent_skill)

        logger.info(f"Assigned skill {skill_id} to agent {agent_id}")
        return agent_skill

    async def update_agent_skill_proficiency(
        self,
        agent_id: UUID,
        skill_id: UUID,
        proficiency_level: int,
        mastery_percentage: float,
    ) -> AgentSkill | None:
        """Update agent's skill proficiency."""
        result = await self.db.execute(
            select(AgentSkill).where(
                and_(
                    AgentSkill.agent_id == agent_id,
                    AgentSkill.skill_id == skill_id,
                )
            )
        )
        agent_skill = result.scalar_one_or_none()

        if not agent_skill:
            return None

        agent_skill.proficiency_level = proficiency_level
        agent_skill.mastery_percentage = Decimal(str(mastery_percentage))
        agent_skill.updated_at = datetime.utcnow()

        await self.db.commit()
        return agent_skill

    async def record_skill_usage(
        self,
        agent_id: UUID,
        skill_id: UUID,
        success: bool,
    ) -> None:
        """Record skill usage for an agent."""
        result = await self.db.execute(
            select(AgentSkill).where(
                and_(
                    AgentSkill.agent_id == agent_id,
                    AgentSkill.skill_id == skill_id,
                )
            )
        )
        agent_skill = result.scalar_one_or_none()

        if agent_skill:
            agent_skill.usage_count += 1
            agent_skill.last_used_at = datetime.utcnow()

            if success:
                agent_skill.success_count += 1
            else:
                agent_skill.failure_count += 1

            await self.db.commit()

    async def get_agent_skills(
        self,
        agent_id: UUID,
        min_proficiency: int | None = None,
    ) -> list[AgentSkill]:
        """Get all skills assigned to an agent."""
        query = select(AgentSkill).where(AgentSkill.agent_id == agent_id)

        if min_proficiency:
            query = query.where(AgentSkill.proficiency_level >= min_proficiency)

        query = query.order_by(desc(AgentSkill.proficiency_level))

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ═════════════════════════════════════════════════════════════════════════
    # REPUTATION SYSTEM (Feature 35)
    # ═════════════════════════════════════════════════════════════════════════

    async def update_reputation(
        self,
        agent_id: UUID,
        change_amount: float,
        reason_type: str,
        description: str | None = None,
        source_agent_id: UUID | None = None,
        task_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Agent:
        """Update agent's reputation score."""
        agent = await self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        previous_score = agent.reputation_score
        new_score = max(0, min(100, previous_score + Decimal(str(change_amount))))

        # Create reputation log
        log = AgentReputationLog(
            agent_id=agent_id,
            previous_score=previous_score,
            new_score=new_score,
            change_amount=Decimal(str(change_amount)),
            reason_type=reason_type,
            description=description,
            source_agent_id=source_agent_id,
            task_id=task_id,
            context=context or {},
        )

        # Update agent score
        agent.reputation_score = new_score

        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(agent)

        logger.info(
            f"Updated reputation for {agent.agent_key}: "
            f"{previous_score} -> {new_score} ({change_amount:+.2f})"
        )
        return agent

    async def get_reputation_history(
        self,
        agent_id: UUID,
        limit: int = 50,
    ) -> list[AgentReputationLog]:
        """Get reputation change history for an agent."""
        result = await self.db.execute(
            select(AgentReputationLog)
            .where(AgentReputationLog.agent_id == agent_id)
            .order_by(desc(AgentReputationLog.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_leaderboard(
        self,
        specialization: str | None = None,
        limit: int = 100,
    ) -> list[Agent]:
        """Get agent leaderboard (Feature 31)."""
        query = select(Agent).where(Agent.is_active)

        if specialization:
            query = query.where(Agent.specialization == specialization)

        query = query.order_by(desc(Agent.reputation_score)).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ═════════════════════════════════════════════════════════════════════════
    # MARKETPLACE (Features 26, 33)
    # ═════════════════════════════════════════════════════════════════════════

    async def create_marketplace_listing(
        self,
        agent_id: UUID,
        title: str,
        description: str | None = None,
        listing_type: str = "skill",
        price: float | None = None,
        offered_skills: list[UUID] | None = None,
        requirements: str | None = None,
        deliverables: str | None = None,
    ) -> AgentMarketplaceListing:
        """Create a marketplace listing."""
        listing = AgentMarketplaceListing(
            agent_id=agent_id,
            title=title,
            description=description,
            listing_type=listing_type,
            price=Decimal(str(price)) if price else None,
            offered_skills=offered_skills or [],
            requirements=requirements,
            deliverables=deliverables,
        )

        self.db.add(listing)
        await self.db.commit()
        await self.db.refresh(listing)

        logger.info(f"Created marketplace listing: {title} by agent {agent_id}")
        return listing

    async def browse_marketplace(
        self,
        listing_type: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        status: str = "active",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AgentMarketplaceListing], int]:
        """Browse marketplace listings."""
        query = select(AgentMarketplaceListing)

        if listing_type:
            query = query.where(AgentMarketplaceListing.listing_type == listing_type)
        if status:
            query = query.where(AgentMarketplaceListing.status == status)
        if min_price:
            query = query.where(AgentMarketplaceListing.price >= min_price)
        if max_price:
            query = query.where(AgentMarketplaceListing.price <= max_price)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)

        # Get results
        query = query.order_by(desc(AgentMarketplaceListing.created_at))
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        listings = result.scalars().all()

        return list(listings), total or 0

    # ═════════════════════════════════════════════════════════════════════════
    # MENTORSHIP (Feature 29)
    # ═════════════════════════════════════════════════════════════════════════

    async def create_mentorship(
        self,
        mentor_id: UUID,
        mentee_id: UUID,
        focus_skills: list[UUID] | None = None,
        goals: list[str] | None = None,
    ) -> AgentMentorship:
        """Create a mentorship relationship."""
        # Validate agents exist
        mentor = await self.get_agent(mentor_id)
        mentee = await self.get_agent(mentee_id)

        if not mentor or not mentee:
            raise ValueError("Mentor or mentee not found")

        if mentor_id == mentee_id:
            raise ValueError("Mentor and mentee cannot be the same agent")

        mentorship = AgentMentorship(
            mentor_id=mentor_id,
            mentee_id=mentee_id,
            focus_skills=focus_skills or [],
            goals=goals or [],
            status=MentorshipStatus.PENDING.value,
        )

        self.db.add(mentorship)
        await self.db.commit()
        await self.db.refresh(mentorship)

        logger.info(f"Created mentorship: {mentor_id} -> {mentee_id}")
        return mentorship

    async def accept_mentorship(self, mentorship_id: UUID) -> AgentMentorship:
        """Accept a mentorship request."""
        mentorship = await self.db.get(AgentMentorship, mentorship_id)
        if not mentorship:
            raise ValueError("Mentorship not found")

        mentorship.status = MentorshipStatus.ACTIVE.value
        mentorship.started_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(mentorship)

        return mentorship

    # ═════════════════════════════════════════════════════════════════════════
    # WISHLIST (Feature 37)
    # ═════════════════════════════════════════════════════════════════════════

    async def add_to_wishlist(
        self,
        agent_id: UUID,
        skill_id: UUID,
        priority: int = 5,
        reason: str | None = None,
        use_case: str | None = None,
    ) -> AgentWishlist:
        """Add a skill to agent's wishlist."""
        # Check if already in wishlist
        existing = await self.db.execute(
            select(AgentWishlist).where(
                and_(
                    AgentWishlist.agent_id == agent_id,
                    AgentWishlist.skill_id == skill_id,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Skill is already in wishlist")

        wishlist_item = AgentWishlist(
            agent_id=agent_id,
            skill_id=skill_id,
            priority=priority,
            reason=reason,
            use_case=use_case,
        )

        self.db.add(wishlist_item)
        await self.db.commit()
        await self.db.refresh(wishlist_item)

        logger.info(f"Added skill {skill_id} to agent {agent_id} wishlist")
        return wishlist_item

    async def get_agent_wishlist(self, agent_id: UUID) -> list[AgentWishlist]:
        """Get agent's skill wishlist."""
        result = await self.db.execute(
            select(AgentWishlist)
            .where(AgentWishlist.agent_id == agent_id)
            .where(not AgentWishlist.is_fulfilled)
            .order_by(AgentWishlist.priority)
        )
        return list(result.scalars().all())

    # ═════════════════════════════════════════════════════════════════════════
    # CERTIFICATES (Feature 32)
    # ═════════════════════════════════════════════════════════════════════════

    async def issue_certificate(
        self,
        agent_id: UUID,
        skill_id: UUID,
        title: str,
        proficiency_level_achieved: int,
        score_achieved: float,
        issued_by: str = "system",
        expires_at: datetime | None = None,
    ) -> AgentCertificate:
        """Issue a skill certificate to an agent."""
        import hashlib

        # Generate certificate key
        cert_key = f"CERT-{agent_id}-{skill_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        # Generate verification hash
        verification_hash = hashlib.sha256(
            f"{agent_id}:{skill_id}:{score_achieved}:{datetime.utcnow()}".encode()
        ).hexdigest()[:16]

        certificate = AgentCertificate(
            agent_id=agent_id,
            skill_id=skill_id,
            certificate_key=cert_key,
            title=title,
            proficiency_level_achieved=proficiency_level_achieved,
            score_achieved=Decimal(str(score_achieved)),
            issued_by=issued_by,
            verification_hash=verification_hash,
            expires_at=expires_at,
        )

        self.db.add(certificate)
        await self.db.commit()
        await self.db.refresh(certificate)

        logger.info(f"Issued certificate {cert_key} to agent {agent_id}")
        return certificate

    async def get_agent_certificates(
        self,
        agent_id: UUID,
    ) -> list[AgentCertificate]:
        """Get all certificates for an agent."""
        result = await self.db.execute(
            select(AgentCertificate)
            .where(AgentCertificate.agent_id == agent_id)
            .order_by(desc(AgentCertificate.issued_at))
        )
        return list(result.scalars().all())
