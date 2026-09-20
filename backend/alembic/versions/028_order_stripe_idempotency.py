"""enforce one funnel order per Stripe Checkout Session."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "028_order_stripe_idempotency"
down_revision: str | Sequence[str] | None = "027_content_batches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_funnel_orders_stripe_session_id",
        "funnel_orders",
        ["stripe_session_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_funnel_orders_stripe_session_id",
        "funnel_orders",
        type_="unique",
    )
