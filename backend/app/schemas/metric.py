from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WeeklyMetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    week_start: date
    opps_found: int | None = 0
    opps_actioned: int | None = 0
    outreach_sent: int | None = 0
    reply_rate: Decimal | None = None
    proposals_won: int | None = 0
    revenue_thb: Decimal | None = None
    ai_cost_usd: Decimal | None = None
    avg_energy_this_week: Decimal | None = None
    created_at: datetime | None = None
