from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class WeeklyMetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    week_start: date
    opps_found: Optional[int] = 0
    opps_actioned: Optional[int] = 0
    outreach_sent: Optional[int] = 0
    reply_rate: Optional[Decimal] = None
    proposals_won: Optional[int] = 0
    revenue_thb: Optional[Decimal] = None
    ai_cost_usd: Optional[Decimal] = None
    avg_energy_this_week: Optional[Decimal] = None
    created_at: Optional[datetime] = None
