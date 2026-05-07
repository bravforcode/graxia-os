"""Add organizations and usage_logs tables

Revision ID: 001
Revises:
Create Date: 2025-01-05 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create organizations table
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("plan", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("monthly_lead_limit", sa.Integer(), nullable=False),
        sa.Column("monthly_ai_credit_cents", sa.Integer(), nullable=False),
        sa.Column("seats", sa.Integer(), nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        sa.CheckConstraint("plan IN ('free','starter','pro')", name="ck_org_plan"),
        sa.CheckConstraint(
            "status IN ('active','trialing','past_due','canceled','suspended')",
            name="ck_org_status",
        ),
    )
    op.create_index(
        op.f("ix_organizations_stripe_customer_id"),
        "organizations",
        ["stripe_customer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organizations_stripe_subscription_id"),
        "organizations",
        ["stripe_subscription_id"],
        unique=False,
    )

    # Create usage_logs table
    op.create_table(
        "usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("feature", sa.String(length=50), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_usage_logs_organization_id"), "usage_logs", ["organization_id"], unique=False
    )
    op.create_index(op.f("ix_usage_logs_feature"), "usage_logs", ["feature"], unique=False)
    op.create_index(op.f("ix_usage_logs_created_at"), "usage_logs", ["created_at"], unique=False)

    # Add organization_id to users table
    op.add_column(
        "users", sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_index(op.f("ix_users_organization_id"), "users", ["organization_id"], unique=False)
    op.create_foreign_key(
        "fk_users_organization_id_organizations",
        "users",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Insert default organization for existing data
    import uuid

    from app.models.organization import Organization
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=op.get_bind())
    session = Session()

    try:
        default_org = Organization(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            name="Legacy Organization",
            slug="legacy",
            plan="free",
            status="active",
        )
        session.add(default_org)
        session.commit()

        # Link existing users to default org
        session.execute(
            sa.text("""
                UPDATE users 
                SET organization_id = :org_id 
                WHERE organization_id IS NULL
            """),
            {"org_id": str(default_org.id)},
        )
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    # Drop foreign keys
    op.drop_constraint(
        "fk_users_organization_id_organizations", table_name="users", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_usage_logs_organization_id_organizations", table_name="usage_logs", type_="foreignkey"
    )

    # Drop indexes
    op.drop_index(op.f("ix_usage_logs_created_at"), table_name="usage_logs")
    op.drop_index(op.f("ix_usage_logs_feature"), table_name="usage_logs")
    op.drop_index(op.f("ix_usage_logs_organization_id"), table_name="usage_logs")
    op.drop_index(op.f("ix_users_organization_id"), table_name="users")
    op.drop_index(op.f("ix_organizations_stripe_subscription_id"), table_name="organizations")
    op.drop_index(op.f("ix_organizations_stripe_customer_id"), table_name="organizations")

    # Drop organization_id from users
    op.drop_column("users", "organization_id")

    # Drop tables
    op.drop_table("usage_logs")
    op.drop_table("organizations")
