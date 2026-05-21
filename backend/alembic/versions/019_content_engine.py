"""content_engine tables + embedding JSONB → vector(1536)

Revision ID: 019_content_engine
Revises: d5bb1ddf06e3
Create Date: 2026-05-09

What this migration does
------------------------
1. Creates the four Content Engine tables if they don't exist:
     content_keywords, content_articles, affiliate_programs,
     affiliate_clicks, revenue_snapshots
2. Adds 'processing' to the status check constraints (Bug Fix #3 back-compat)
3. Converts content_articles.embedding from JSONB → vector(1536) and
   creates an IVFFlat cosine index for fast duplicate detection.
   The extension is already enabled by 005_pgvector.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers
revision: str = "019_content_engine"
down_revision: str | None = "d5bb1ddf06e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table_exists(table_name: str) -> bool:
    bind = op.get_context().bind
    return sa.inspect(bind).has_table(table_name)


def upgrade() -> None:
    # ── 1. Create content_keywords ──────────────────────────────────────────
    if not _table_exists("content_keywords"):
        op.create_table(
            "content_keywords",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("keyword", sa.String(500), nullable=False),
            sa.Column("keyword_th", sa.String(500)),
            sa.Column("site", sa.String(20), nullable=False, index=True),
            sa.Column("language", sa.String(5), nullable=False, server_default="en"),
            sa.Column("content_type", sa.String(20), server_default="article"),
            sa.Column("search_volume", sa.Integer()),
            sa.Column("keyword_difficulty", sa.Integer()),
            sa.Column("cpc_usd", sa.Numeric(6, 2)),
            sa.Column("search_intent", sa.String(50)),
            sa.Column("status", sa.String(20), server_default="pending", index=True),
            sa.Column("priority", sa.Integer(), server_default="5"),
            sa.Column("retry_count", sa.Integer(), server_default="0"),
            sa.Column("error_message", sa.Text()),
            sa.Column("article_id", sa.String(36)),
            sa.Column("article_url", sa.String(1024)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("processed_at", sa.DateTime(timezone=True)),
            sa.Column("published_at", sa.DateTime(timezone=True)),
            sa.CheckConstraint("site IN ('site_a','site_b')", name="ck_kw_site"),
            sa.CheckConstraint("language IN ('en','th')", name="ck_kw_language"),
            sa.CheckConstraint(
                "status IN ('pending','processing','draft','review','approved','published','archived','failed')",
                name="ck_kw_status",
            ),
            sa.CheckConstraint(
                "content_type IN ('article','review','comparison','listicle','how_to','faq')",
                name="ck_kw_content_type",
            ),
        )

    # ── 2. Create content_articles ──────────────────────────────────────────
    if not _table_exists("content_articles"):
        op.create_table(
            "content_articles",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("site", sa.String(20), nullable=False, index=True),
            sa.Column("slug", sa.String(500), nullable=False),
            sa.Column("title", sa.String(500), nullable=False),
            sa.Column("title_th", sa.String(500)),
            sa.Column("language", sa.String(5), server_default="en"),
            sa.Column("content_type", sa.String(20), server_default="article"),
            sa.Column("meta_title", sa.String(120)),
            sa.Column("meta_description", sa.String(300)),
            sa.Column("target_keyword", sa.String(500)),
            sa.Column("secondary_keywords", sa.JSON()),
            sa.Column("schema_type", sa.String(50), server_default="Article"),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("hero_image_url", sa.String(1024)),
            sa.Column("word_count", sa.Integer()),
            sa.Column("reading_time", sa.Integer()),
            sa.Column("affiliate_programs_used", sa.JSON()),
            sa.Column("views_total", sa.Integer(), server_default="0"),
            sa.Column("views_30d", sa.Integer(), server_default="0"),
            sa.Column("unique_visitors", sa.Integer(), server_default="0"),
            sa.Column("avg_time_on_page", sa.Numeric(6, 1)),
            sa.Column("bounce_rate", sa.Numeric(5, 2)),
            sa.Column("search_impressions_30d", sa.Integer(), server_default="0"),
            sa.Column("search_clicks_30d", sa.Integer(), server_default="0"),
            sa.Column("avg_search_position", sa.Numeric(5, 1)),
            sa.Column("ctr", sa.Numeric(5, 4)),
            sa.Column("affiliate_clicks", sa.Integer(), server_default="0"),
            sa.Column("affiliate_revenue", sa.Numeric(10, 2), server_default="0.00"),
            sa.Column("status", sa.String(20), server_default="draft", index=True),
            sa.Column("needs_refresh", sa.Boolean(), server_default="false"),
            sa.Column("reviewed_by", sa.String(255)),
            sa.Column("review_notes", sa.Text()),
            sa.Column("published_url", sa.String(1024)),
            # embedding created as vector(1536) from the start on fresh installs
            sa.Column("embedding", Vector(1536)),
            sa.Column("generation_model", sa.String(100)),
            sa.Column("generation_tokens", sa.Integer()),
            sa.Column("generation_cost_usd", sa.Numeric(8, 6)),
            sa.Column("content_hash", sa.String(64)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("published_at", sa.DateTime(timezone=True)),
            sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.CheckConstraint("site IN ('site_a','site_b')", name="ck_article_site"),
            sa.CheckConstraint("language IN ('en','th')", name="ck_article_language"),
            sa.CheckConstraint(
                "status IN ('pending','processing','draft','review','approved','published','archived','failed')",
                name="ck_article_status",
            ),
            sa.CheckConstraint(
                "content_type IN ('article','review','comparison','listicle','how_to','faq')",
                name="ck_article_content_type",
            ),
        )
        # IVFFlat cosine index for semantic search + duplicate detection
        op.execute("""
            CREATE INDEX IF NOT EXISTS idx_content_articles_embedding
            ON content_articles USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """)
    else:
        # ── 3. Existing install: JSONB → vector migration ──────────────────
        # Check if column is still JSONB (old installs from initial scaffold)
        conn = op.get_bind()
        result = conn.execute(sa.text("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'content_articles' AND column_name = 'embedding'
        """)).fetchone()

        if result and result[0] in ("jsonb", "json"):
            op.execute("ALTER TABLE content_articles DROP COLUMN IF EXISTS embedding")
            op.execute("ALTER TABLE content_articles ADD COLUMN embedding vector(1536)")
            op.execute("""
                CREATE INDEX IF NOT EXISTS idx_content_articles_embedding
                ON content_articles USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            """)

        # ── 4. Add 'processing' to check constraints (if not already there) ──
        # Drop and recreate to add the new value safely
        try:
            op.drop_constraint("ck_article_status", "content_articles", type_="check")
        except Exception:
            pass
        op.create_check_constraint(
            "ck_article_status",
            "content_articles",
            "status IN ('pending','processing','draft','review','approved','published','archived','failed')",
        )
        try:
            op.drop_constraint("ck_kw_status", "content_keywords", type_="check")
        except Exception:
            pass
        op.create_check_constraint(
            "ck_kw_status",
            "content_keywords",
            "status IN ('pending','processing','draft','review','approved','published','archived','failed')",
        )

    # ── 5. Create affiliate_programs ────────────────────────────────────────
    if not _table_exists("affiliate_programs"):
        op.create_table(
            "affiliate_programs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("slug", sa.String(100), unique=True, nullable=False, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("network", sa.String(100)),
            sa.Column("category", sa.String(100)),
            sa.Column("commission_type", sa.String(50)),
            sa.Column("commission_value", sa.Numeric(8, 2)),
            sa.Column("cookie_days", sa.Integer()),
            sa.Column("base_url", sa.String(2048), nullable=False),
            sa.Column("dashboard_url", sa.String(2048)),
            sa.Column("cloaked_path", sa.String(500)),
            sa.Column("site", sa.String(20), index=True),
            sa.Column("status", sa.String(20), server_default="active"),
            sa.Column("last_checked", sa.DateTime(timezone=True)),
            sa.Column("clicks_30d", sa.Integer(), server_default="0"),
            sa.Column("conversions_30d", sa.Integer(), server_default="0"),
            sa.Column("revenue_30d", sa.Numeric(10, 2), server_default="0.00"),
            sa.Column("trigger_keywords", sa.JSON()),
            sa.Column("cta_text", sa.String(500)),
            sa.Column("cta_text_th", sa.String(500)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.CheckConstraint("status IN ('active','paused','broken')", name="ck_aff_status"),
            sa.CheckConstraint("site IN ('site_a','site_b')", name="ck_aff_site"),
        )

    # ── 6. Create affiliate_clicks ──────────────────────────────────────────
    if not _table_exists("affiliate_clicks"):
        op.create_table(
            "affiliate_clicks",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("program_id", sa.String(36),
                      sa.ForeignKey("affiliate_programs.id", ondelete="SET NULL")),
            sa.Column("program_slug", sa.String(100), nullable=False, index=True),
            sa.Column("article_id", sa.String(36),
                      sa.ForeignKey("content_articles.id", ondelete="SET NULL")),
            sa.Column("article_slug", sa.String(500)),
            sa.Column("site", sa.String(20), index=True),
            sa.Column("session_id", sa.String(255)),
            sa.Column("country_code", sa.String(5)),
            sa.Column("device_type", sa.String(20)),
            sa.Column("referrer", sa.String(2048)),
            sa.Column("clicked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── 7. Create revenue_snapshots ─────────────────────────────────────────
    if not _table_exists("revenue_snapshots"):
        op.create_table(
            "revenue_snapshots",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("date", sa.DateTime(timezone=True), nullable=False, unique=True),
            sa.Column("affiliate_revenue", sa.Numeric(10, 2), server_default="0.00"),
            sa.Column("digital_revenue", sa.Numeric(10, 2), server_default="0.00"),
            sa.Column("ad_revenue", sa.Numeric(10, 2), server_default="0.00"),
            sa.Column("store_revenue", sa.Numeric(10, 2), server_default="0.00"),
            sa.Column("total_revenue", sa.Numeric(10, 2), server_default="0.00"),
            sa.Column("site_a_revenue", sa.Numeric(10, 2), server_default="0.00"),
            sa.Column("site_b_revenue", sa.Numeric(10, 2), server_default="0.00"),
            sa.Column("total_pageviews", sa.Integer(), server_default="0"),
            sa.Column("total_sessions", sa.Integer(), server_default="0"),
            sa.Column("new_visitors", sa.Integer(), server_default="0"),
            sa.Column("new_leads", sa.Integer(), server_default="0"),
            sa.Column("total_orders", sa.Integer(), server_default="0"),
            sa.Column("avg_order_value", sa.Numeric(8, 2)),
            sa.Column("articles_published", sa.Integer(), server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("revenue_snapshots")
    op.drop_table("affiliate_clicks")
    op.drop_table("affiliate_programs")
    op.execute("DROP INDEX IF EXISTS idx_content_articles_embedding")
    op.drop_table("content_keywords")
    op.drop_table("content_articles")
