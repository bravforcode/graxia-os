"""enterprise baseline

Revision ID: 001_enterprise_baseline
Revises:
Create Date: 2026-04-08
"""

from collections.abc import Sequence

from alembic import op

from app.models import Base

# revision identifiers, used by Alembic.
revision: str = "001_enterprise_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
