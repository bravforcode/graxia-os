"""final_head_merge

Revision ID: cef7acf8e4ed
Revises: 018_add_composite_query_indexes, 019_content_engine, 21a5f8dc21ec
Create Date: 2026-05-09 19:24:02.897582

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cef7acf8e4ed'
down_revision: Union[str, None] = ('018_add_composite_query_indexes', '019_content_engine', '21a5f8dc21ec')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
