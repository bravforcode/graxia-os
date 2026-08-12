"""add pgvector

Revision ID: 005
Revises: 004_users_social_cols
Create Date: 2026-04-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: str | None = "004_users_social_cols"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_knowledge_category", "knowledge_items", type_="check")
    op.create_check_constraint(
        "ck_knowledge_category",
        "knowledge_items",
        "category IN ('project','proposal_template','bio','skill_description','lesson','case_study','testimonial','pitch_snippet','objection_response','playbook','failure_analysis','vault_note','research')",
    )

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Idempotent column adds — earlier baseline migrations may already have
    # created these columns on fresh databases.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("knowledge_items")}
    for column in (
        sa.Column("embedding", Vector(768)),
        sa.Column("chunk_hash", sa.String(64)),
        sa.Column("chunk_index", sa.Integer()),
        sa.Column("source_path", sa.String(512)),
    ):
        if column.name not in existing:
            op.add_column("knowledge_items", column)
    op.execute("""
      CREATE INDEX IF NOT EXISTS knowledge_embedding_hnsw
      ON knowledge_items USING hnsw (embedding vector_cosine_ops)
      WITH (m=16, ef_construction=64)
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_items_chunk_hash "
        "ON knowledge_items (chunk_hash)"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_items_chunk_hash"), table_name="knowledge_items")
    op.execute("DROP INDEX IF EXISTS knowledge_embedding_hnsw")
    op.drop_column("knowledge_items", "source_path")
    op.drop_column("knowledge_items", "chunk_index")
    op.drop_column("knowledge_items", "chunk_hash")
    op.drop_column("knowledge_items", "embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")

    op.drop_constraint("ck_knowledge_category", "knowledge_items", type_="check")
    op.create_check_constraint(
        "ck_knowledge_category",
        "knowledge_items",
        "category IN ('project','proposal_template','bio','skill_description','lesson','case_study','testimonial','pitch_snippet','objection_response','playbook','failure_analysis')",
    )
