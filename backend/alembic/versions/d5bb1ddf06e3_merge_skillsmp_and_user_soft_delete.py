"""merge skillsmp and user soft delete

Revision ID: d5bb1ddf06e3
Revises: 013_add_skillsmp_integration, 015_add_user_soft_delete
Create Date: 2026-04-30 05:18:38.047350

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "d5bb1ddf06e3"
down_revision: str | None = ("013_add_skillsmp_integration", "015_add_user_soft_delete")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
