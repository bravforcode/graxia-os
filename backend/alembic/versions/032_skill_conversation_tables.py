"""create persistent conversation-memory tables used by the runtime.

The ORM models predate the consolidated Alembic chain.  Without this
revision the readiness probe correctly reports missing tables and privacy
export/erasure paths fail as soon as conversation data is requested.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "032_skill_conversation_tables"
down_revision: str | Sequence[str] | None = "026_audit_query_contract"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "conversation_sessions",
    "conversation_messages",
    "conversation_context_windows",
    "conversation_memory_extracts",
    "skill_context_preferences",
)


def _json_default(value: str) -> sa.TextClause:
    return sa.text(f"'{value}'::jsonb")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {name: inspector.has_table(name) for name in _TABLES}

    if all(existing.values()):
        # Some older Graxia deployments create ORM tables before Alembic.
        # Preserve that data and treat the schema as already satisfied.
        return
    if any(existing.values()):
        raise RuntimeError(
            "partial conversation-memory schema detected; refusing to alter it"
        )

    required_parent_tables = ("agents", "users", "skillsmp_skills")
    missing_parents = [
        name for name in required_parent_tables if not inspector.has_table(name)
    ]
    if missing_parents:
        raise RuntimeError(
            "conversation-memory prerequisites are missing: "
            + ", ".join(missing_parents)
        )

    uuid_type = postgresql.UUID(as_uuid=True)
    json_type = postgresql.JSONB
    timestamp = sa.DateTime(timezone=True)

    op.create_table(
        "conversation_sessions",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("session_key", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("agent_id", uuid_type, nullable=True),
        sa.Column("user_id", uuid_type, nullable=True),
        sa.Column("primary_skill_id", uuid_type, nullable=True),
        sa.Column("max_context_messages", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("context_window_tokens", sa.Integer(), nullable=False, server_default="4000"),
        sa.Column("enable_persistent_memory", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("memory_retention_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("key_entities", json_type, nullable=False, server_default=_json_default("[]")),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_message_at", timestamp, nullable=True),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("archived_at", timestamp, nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["primary_skill_id"], ["skillsmp_skills.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_key", name="uq_conversation_sessions_session_key"),
    )
    op.create_index("ix_conversation_sessions_session_key", "conversation_sessions", ["session_key"], unique=True)
    op.create_index("ix_conversation_sessions_agent_id", "conversation_sessions", ["agent_id"])
    op.create_index("ix_conversation_sessions_user_id", "conversation_sessions", ["user_id"])
    op.create_index("ix_conversation_sessions_primary_skill_id", "conversation_sessions", ["primary_skill_id"])

    op.create_table(
        "conversation_messages",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("session_id", uuid_type, nullable=False),
        sa.Column("message_number", sa.Integer(), nullable=False),
        sa.Column("sender_type", sa.String(length=20), nullable=False),
        sa.Column("sender_id", uuid_type, nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False, server_default="text"),
        sa.Column("invoked_skill_id", uuid_type, nullable=True),
        sa.Column("skill_input", json_type, nullable=False, server_default=_json_default("{}")),
        sa.Column("skill_output", json_type, nullable=False, server_default=_json_default("{}")),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("context_included", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("context_messages", json_type, nullable=False, server_default=_json_default("[]")),
        sa.Column("generation_duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["invoked_skill_id"], ["skillsmp_skills.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "message_number", name="uq_conversation_messages_session_number"
        ),
    )
    op.create_index("ix_conversation_messages_session_id", "conversation_messages", ["session_id"])
    op.create_index("ix_conversation_messages_created_at", "conversation_messages", ["created_at"])

    op.create_table(
        "conversation_context_windows",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("session_id", uuid_type, nullable=False),
        sa.Column("window_start_message", sa.Integer(), nullable=False),
        sa.Column("window_end_message", sa.Integer(), nullable=False),
        sa.Column("messages_summary", sa.Text(), nullable=False),
        sa.Column("key_facts", json_type, nullable=False, server_default=_json_default("[]")),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("relevance_scores", json_type, nullable=False, server_default=_json_default("{}")),
        sa.Column("computed_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_context_windows_session_id",
        "conversation_context_windows",
        ["session_id"],
    )

    op.create_table(
        "conversation_memory_extracts",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("session_id", uuid_type, nullable=False),
        sa.Column("fact_type", sa.String(length=50), nullable=False),
        sa.Column("fact_key", sa.String(length=255), nullable=False),
        sa.Column("fact_value", sa.Text(), nullable=False),
        sa.Column("source_message_ids", json_type, nullable=False, server_default=_json_default("[]")),
        sa.Column("extraction_confidence", sa.Numeric(precision=3, scale=2), nullable=False, server_default="0.8"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", timestamp, nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_accessed_at", timestamp, nullable=True),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversation_memory_extracts_session_id", "conversation_memory_extracts", ["session_id"])
    op.create_index(
        "ix_memory_extracts_session_key",
        "conversation_memory_extracts",
        ["session_id", "fact_key"],
    )

    op.create_table(
        "skill_context_preferences",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("agent_id", uuid_type, nullable=False),
        sa.Column("skill_id", uuid_type, nullable=True),
        sa.Column("default_context_variables", json_type, nullable=False, server_default=_json_default("{}")),
        sa.Column("preferred_conversation_style", sa.String(length=50), nullable=False, server_default="professional"),
        sa.Column("auto_invoke_on_keywords", json_type, nullable=False, server_default=_json_default("[]")),
        sa.Column("require_confirmation", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("remember_preferences", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("share_context_across_sessions", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skillsmp_skills.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "skill_id", name="uq_context_preferences_agent_skill"),
    )
    op.create_index("ix_skill_context_preferences_agent_id", "skill_context_preferences", ["agent_id"])


def downgrade() -> None:
    # Preserve conversation data during rollback. A deliberate data migration
    # is required before removing these tables from a live tenant.
    return
