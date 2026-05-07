"""
Add SkillsMP Integration Tables

Revision ID: 013
Revises: 012_revenue_os_v12
Create Date: 2026-04-29 03:30:00.000000
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "013_add_skillsmp_integration"
down_revision: str | None = "012_revenue_os_v12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create skillsmp_skills table
    op.create_table(
        "skillsmp_skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("external_id", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column(
            "source_type", sa.String(50), nullable=False, index=True
        ),  # openclaw, claude, codex, hermes, tool, dev, context
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),  # Full markdown content
        sa.Column(
            "content_embedding", postgresql.ARRAY(sa.Float()), nullable=True
        ),  # Vector for RAG (1536-dim)
        sa.Column("skill_metadata", postgresql.JSONB(astext_type=sa.Text()), default=dict),
        # Learning & Evolution fields
        sa.Column("usage_count", sa.Integer(), default=0),
        sa.Column("success_rate", sa.Numeric(5, 2), default=0.00),  # 0-100%
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effectiveness_score", sa.Numeric(5, 2), default=0.00),
        sa.Column("ai_improved_version", sa.Text(), nullable=True),  # AI-generated improvements
        # Auto-learning fields
        sa.Column(
            "related_skill_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), default=list
        ),
        sa.Column("trigger_patterns", postgresql.ARRAY(sa.String()), default=list),  # When to use
        sa.Column("context_tags", postgresql.ARRAY(sa.String()), default=list),  # Domain tags
        # Sync metadata
        sa.Column("first_synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("auto_sync_enabled", sa.Boolean(), default=True),
        sa.Column("is_deleted_at_source", sa.Boolean(), default=False),
        # Version control
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("previous_versions", postgresql.JSONB(astext_type=sa.Text()), default=list),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # Create indexes
    op.create_index("idx_skillsmp_type", "skillsmp_skills", ["source_type"])
    op.create_index("idx_skillsmp_deleted", "skillsmp_skills", ["is_deleted_at_source"])
    op.create_index("idx_skillsmp_usage", "skillsmp_skills", ["usage_count", "effectiveness_score"])
    op.create_index(
        "idx_skillsmp_tags", "skillsmp_skills", ["context_tags"], postgresql_using="gin"
    )
    op.create_index(
        "idx_skillsmp_triggers", "skillsmp_skills", ["trigger_patterns"], postgresql_using="gin"
    )
    op.create_index(
        "idx_skillsmp_metadata", "skillsmp_skills", ["skill_metadata"], postgresql_using="gin"
    )

    # Create skill_learning_log table
    op.create_table(
        "skill_learning_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "skill_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("skillsmp_skills.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "learning_type", sa.String(50), nullable=False, index=True
        ),  # usage, improvement, creation
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("before_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create index on learning log
    op.create_index("idx_learning_log_skill", "skill_learning_log", ["skill_id", "learning_type"])
    op.create_index("idx_learning_log_created", "skill_learning_log", ["created_at"])

    # Create skill_recommendations table for caching recommendations
    op.create_table(
        "skill_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "context_hash", sa.String(64), nullable=False, index=True
        ),  # Hash of query context
        sa.Column(
            "recommended_skill_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False
        ),
        sa.Column(
            "scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),  # Score details
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create skill_invocations table for tracking AI usage
    op.create_table(
        "skill_invocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "skill_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("skillsmp_skills.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "invocation_type", sa.String(50), nullable=False
        ),  # direct, rag, content_injection
        sa.Column("task_context", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("feedback_rating", sa.Integer(), nullable=True),  # 1-5 rating
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("idx_invocations_skill", "skill_invocations", ["skill_id", "created_at"])
    op.create_index("idx_invocations_type", "skill_invocations", ["invocation_type", "success"])


def downgrade() -> None:
    op.drop_table("skill_invocations")
    op.drop_table("skill_recommendations")
    op.drop_table("skill_learning_log")
    op.drop_table("skillsmp_skills")
