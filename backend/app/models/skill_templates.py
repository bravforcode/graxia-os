"""
Skill Templates — Feature 5
Template inheritance and marketplace for skills
"""

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as SQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SkillTemplate(Base):
    """
    Reusable skill templates

    Feature 5: Skill Templates
    """

    __tablename__ = "skill_templates"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    template_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Template content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list[dict]] = mapped_column(
        JSONB, default=list
    )  # [{name, type, default, description}]

    # Inheritance
    parent_template_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skill_templates.id"), nullable=True
    )
    inheritance_chain: Mapped[list[UUIDType]] = mapped_column(
        JSONB, default=list
    )  # List of parent template IDs

    # Template metadata
    category: Mapped[str | None] = mapped_column(String(100), index=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # Marketplace
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    author_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    # Usage
    usage_count: Mapped[int] = mapped_column(Integer, default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class SkillTemplateInstance(Base):
    """
    Skill created from a template
    """

    __tablename__ = "skill_template_instances"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Template reference
    template_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skill_templates.id"), nullable=False, index=True
    )

    # Created skill
    skill_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=False, unique=True
    )

    # Instance configuration
    variable_values: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict
    )  # {variable_name: value}
    customizations: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=dict
    )  # Custom changes made after instantiation

    created_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
