"""merge funnel foundation and performance indexes

Revision ID: 1e9db9a3b0ba
Revises: 020_add_funnel_foundation, 6dd9193e3e73
Create Date: 2026-05-22 02:35:35.080581

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e9db9a3b0ba'
down_revision: Union[str, None] = ('020_add_funnel_foundation', '6dd9193e3e73')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
