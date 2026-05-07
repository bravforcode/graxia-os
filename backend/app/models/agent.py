"""
Agent Ecosystem Models — Features 26-40
Core agent system with teams, reputation, and marketplace
"""

import uuid
from datetime import datetime, UTC
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import (
    UUID as SQLUUID,
)
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# ═══════════════════════════════════════════════════════════════════════════════
# AGENT TABLE — Core agent entity (Feature 26)
# ═══════════════════════════════════════════════════════════════════════════════


class AgentStatus(StrEnum):
    """Agent lifecycle status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    TRAINING = "training"
    RETIRED = "retired"


class Agent(Base):
    """
    Agent Entity — The heart of the Agent Ecosystem

    Features:
    - 26: Agent Registry
    - 28: Agent Specialization
    - 35: Agent Reputation System
    - 36: Agent Skill History
    - 38: Agent Custom Skills
    """

    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("agent_key", name="uq_agent_key"),)

    # Primary Fields
    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_key: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )  # Unique identifier like "agent-001"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Status & Lifecycle
    status: Mapped[str] = mapped_column(String(50), default=AgentStatus.ACTIVE, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Specialization (Feature 28)
    specialization: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # e.g., "frontend", "backend", "data-analysis"
    expertise_domains: Mapped[list[str] | None] = mapped_column(
        JSONB, default=list
    )  # List of expertise areas

    # Reputation System (Feature 35)
    reputation_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("50.00")
    )  # 0-100
    total_tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))  # 0-100%

    # Performance Metrics
    avg_task_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Collaboration (Feature 27)
    collaboration_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    team_player_rating: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), default=Decimal("0.00")
    )  # 0-5 stars

    # Custom Configuration
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    preferences: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Metadata
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    skills: Mapped[list["AgentSkill"]] = relationship(
        "AgentSkill", back_populates="agent", cascade="all, delete-orphan"
    )
    team_memberships: Mapped[list["AgentTeamMember"]] = relationship(
        "AgentTeamMember", back_populates="agent", cascade="all, delete-orphan"
    )
    reputation_history: Mapped[list["AgentReputationLog"]] = relationship(
        "AgentReputationLog", back_populates="agent", cascade="all, delete-orphan"
    )
    marketplace_listings: Mapped[list["AgentMarketplaceListing"]] = relationship(
        "AgentMarketplaceListing", back_populates="agent"
    )
    collaborations: Mapped[list["AgentCollaboration"]] = relationship(
        "AgentCollaboration", secondary="agent_collaboration_members", back_populates="agents"
    )
    wishlist: Mapped[list["AgentWishlist"]] = relationship(
        "AgentWishlist", back_populates="agent", cascade="all, delete-orphan"
    )
    certificates: Mapped[list["AgentCertificate"]] = relationship(
        "AgentCertificate", back_populates="agent", cascade="all, delete-orphan"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT TEAM — Team management (Feature 34)
# ═══════════════════════════════════════════════════════════════════════════════


class AgentTeam(Base):
    """
    Agent Team — Collaborative teams of agents

    Features:
    - 34: Agent Teams
    - 40: Multi-Agent Orchestration
    """

    __tablename__ = "agent_teams"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Team Configuration
    team_type: Mapped[str] = mapped_column(String(50), default="squad")  # squad, guild, task-force
    max_members: Mapped[int] = mapped_column(Integer, default=10)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)

    # Performance
    collective_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0)

    # Metadata
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    members: Mapped[list["AgentTeamMember"]] = relationship(
        "AgentTeamMember", back_populates="team", cascade="all, delete-orphan"
    )


class AgentTeamMember(Base):
    """Agent membership in a team with roles."""

    __tablename__ = "agent_team_members"
    __table_args__ = (UniqueConstraint("agent_id", "team_id", name="uq_team_member"),)

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    team_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agent_teams.id"), nullable=False
    )

    # Role in team
    role: Mapped[str] = mapped_column(
        String(50), default="member"
    )  # leader, member, specialist, mentor

    # Join date
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Relationships
    agent: Mapped[Agent] = relationship("Agent", back_populates="team_memberships")
    team: Mapped[AgentTeam] = relationship("AgentTeam", back_populates="members")


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT SKILLS INVENTORY — Skills per agent (Feature 36, 38)
# ═══════════════════════════════════════════════════════════════════════════════


class AgentSkill(Base):
    """
    Agent's Skill Inventory

    Tracks which skills an agent has and their proficiency.
    Features:
    - 36: Agent Skill History
    - 38: Agent Custom Skills
    """

    __tablename__ = "agent_skills"
    __table_args__ = (UniqueConstraint("agent_id", "skill_id", name="uq_agent_skill"),)

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    skill_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=False
    )

    # Proficiency & Mastery
    proficiency_level: Mapped[int] = mapped_column(Integer, default=1)  # 1-10 scale
    mastery_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00")
    )  # 0-100%

    # Usage Tracking
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)

    # Custom Settings
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    custom_triggers: Mapped[list[str] | None] = mapped_column(JSONB, default=list)

    # Learning Progress
    learning_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    agent: Mapped[Agent] = relationship("Agent", back_populates="skills")


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT REPUTATION — Reputation tracking (Feature 35)
# ═══════════════════════════════════════════════════════════════════════════════


class AgentReputationLog(Base):
    """
    Agent Reputation History

    Tracks all reputation changes for transparency.
    Feature 35: Agent Reputation System
    """

    __tablename__ = "agent_reputation_logs"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )

    # Change Details
    previous_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    new_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    change_amount: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    # Reason
    reason_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # task_completed, collaboration, feedback, violation
    description: Mapped[str | None] = mapped_column(Text)

    # Source
    source_agent_id: Mapped[UUIDType | None] = mapped_column(SQLUUID(as_uuid=True), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(255))

    # Context
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    # Relationships
    agent: Mapped[Agent] = relationship("Agent", back_populates="reputation_history")


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT MARKETPLACE — Skill marketplace (Feature 26, 33)
# ═══════════════════════════════════════════════════════════════════════════════


class MarketplaceListingStatus(StrEnum):
    """Marketplace listing status."""

    ACTIVE = "active"
    SOLD = "sold"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"
    PENDING = "pending"


class AgentMarketplaceListing(Base):
    """
    Agent Skill Marketplace Listing

    Features:
    - 26: Agent Skill Marketplace
    - 33: Agent Hiring System
    """

    __tablename__ = "agent_marketplace_listings"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )

    # Listing Details
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    listing_type: Mapped[str] = mapped_column(
        String(50), default="skill"
    )  # skill, service, collaboration

    # Pricing
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    is_negotiable: Mapped[bool] = mapped_column(Boolean, default=False)

    # Skills Offered
    offered_skills: Mapped[list[UUIDType] | None] = mapped_column(
        JSONB, default=list
    )  # List of skill IDs

    # Status
    status: Mapped[str] = mapped_column(String(50), default=MarketplaceListingStatus.ACTIVE)

    # Availability
    available_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Metrics
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    inquiries_count: Mapped[int] = mapped_column(Integer, default=0)
    sales_count: Mapped[int] = mapped_column(Integer, default=0)

    # Metadata
    requirements: Mapped[str | None] = mapped_column(Text)
    deliverables: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    agent: Mapped[Agent] = relationship("Agent", back_populates="marketplace_listings")


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT COLLABORATION — Collaboration sessions (Feature 27, 40)
# ═══════════════════════════════════════════════════════════════════════════════


class CollaborationStatus(StrEnum):
    """Collaboration session status."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentCollaboration(Base):
    """
    Multi-Agent Collaboration Session

    Features:
    - 27: Agent Collaboration
    - 40: Multi-Agent Orchestration
    """

    __tablename__ = "agent_collaborations"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Session Details
    session_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Task Context
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    task_description: Mapped[str | None] = mapped_column(Text)

    # Orchestration
    orchestrator_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), nullable=True
    )
    parent_collaboration_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agent_collaborations.id"), nullable=True
    )

    # Status & Progress
    status: Mapped[str] = mapped_column(String(50), default=CollaborationStatus.PENDING)
    progress_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))

    # Results
    result_summary: Mapped[str | None] = mapped_column(Text)
    result_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Performance
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    agents: Mapped[list[Agent]] = relationship(
        "Agent", secondary="agent_collaboration_members", back_populates="collaborations"
    )


class AgentCollaborationMember(Base):
    """Agent participation in a collaboration."""

    __tablename__ = "agent_collaboration_members"
    __table_args__ = (
        UniqueConstraint("collaboration_id", "agent_id", name="uq_collaboration_member"),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    collaboration_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agent_collaborations.id"), nullable=False
    )
    agent_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )

    # Role in collaboration
    role: Mapped[str] = mapped_column(
        String(50), default="contributor"
    )  # orchestrator, contributor, reviewer

    # Contribution
    contribution_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0)

    # Status
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    messages: Mapped[list["AgentCollaborationMessage"]] = relationship(
        "AgentCollaborationMessage", back_populates="member"
    )


class AgentCollaborationMessage(Base):
    """Messages exchanged during collaboration."""

    __tablename__ = "agent_collaboration_messages"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agent_collaboration_members.id"), nullable=False
    )

    # Message Content
    message_type: Mapped[str] = mapped_column(
        String(50), default="text"
    )  # text, skill_share, result, decision
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Context
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    # Relationships
    member: Mapped[AgentCollaborationMember] = relationship(
        "AgentCollaborationMember", back_populates="messages"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT MENTORSHIP — Mentorship relationships (Feature 29)
# ═══════════════════════════════════════════════════════════════════════════════


class MentorshipStatus(StrEnum):
    """Mentorship relationship status."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    TERMINATED = "terminated"


class AgentMentorship(Base):
    """
    Agent Mentorship Relationship

    Feature 29: Agent Mentorship
    """

    __tablename__ = "agent_mentorships"
    __table_args__ = (UniqueConstraint("mentor_id", "mentee_id", name="uq_mentorship"),)

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mentor_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    mentee_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )

    # Focus Areas
    focus_skills: Mapped[list[UUIDType] | None] = mapped_column(JSONB, default=list)
    goals: Mapped[list[str] | None] = mapped_column(JSONB, default=list)

    # Status
    status: Mapped[str] = mapped_column(String(50), default=MentorshipStatus.PENDING)

    # Progress
    progress_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    sessions_completed: Mapped[int] = mapped_column(Integer, default=0)
    skills_taught: Mapped[int] = mapped_column(Integer, default=0)

    # Feedback
    mentor_rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    mentee_rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))

    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT WISHLIST — Skills agents want to learn (Feature 37)
# ═══════════════════════════════════════════════════════════════════════════════


class AgentWishlist(Base):
    """
    Agent's Skill Wishlist

    Feature 37: Agent Skill Wishlist
    """

    __tablename__ = "agent_wishlists"
    __table_args__ = (UniqueConstraint("agent_id", "skill_id", name="uq_agent_wishlist"),)

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    skill_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=False
    )

    # Priority
    priority: Mapped[int] = mapped_column(Integer, default=5)  # 1-10

    # Reason
    reason: Mapped[str | None] = mapped_column(Text)
    use_case: Mapped[str | None] = mapped_column(Text)

    # Status
    is_fulfilled: Mapped[bool] = mapped_column(Boolean, default=False)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Relationships
    agent: Mapped[Agent] = relationship("Agent", back_populates="wishlist")


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT CERTIFICATES — Skill certificates (Feature 32)
# ═══════════════════════════════════════════════════════════════════════════════


class AgentCertificate(Base):
    """
    Agent Skill Certificate

    Feature 32: Agent Skill Certificates
    """

    __tablename__ = "agent_certificates"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    skill_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=False
    )

    # Certificate Details
    certificate_key: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # Achievement
    proficiency_level_achieved: Mapped[int] = mapped_column(Integer, default=1)
    score_achieved: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    # Verification
    issued_by: Mapped[str] = mapped_column(String(255))  # system, mentor, exam
    verification_hash: Mapped[str | None] = mapped_column(String(255))

    # Metadata
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    # Timestamps
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    agent: Mapped[Agent] = relationship("Agent", back_populates="certificates")
