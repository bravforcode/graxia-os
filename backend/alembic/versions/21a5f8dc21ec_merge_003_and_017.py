"""merge_003_and_017

Revision ID: 21a5f8dc21ec
Revises: 003, 017_add_gin_fulltext_indexes
Create Date: 2026-05-06 02:36:26.629874

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '21a5f8dc21ec'
down_revision: str | None = ('003', '017_add_gin_fulltext_indexes')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
