from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    title: str
    description: str | None = None
    source_url: str | None = None
    source_platform: str | None = None
    deadline: date | None = None
    total_score: Decimal | None = None
    scoring_rationale: str | None = None
    red_flags: list | None = []
    decision: str | None = None
    decision_confidence: Decimal | None = None
    decision_reasoning: str | None = None
    action_priority: str | None = None
    status: str | None = None
    prize_amount: str | None = None
    tags: list | None = []
    is_student_eligible: bool | None = None
    location_type: str | None = None
    fit_summary: str | None = None
    found_at: datetime | None = None
    money_score: int | None = None
    brand_score: int | None = None
    network_score: int | None = None
    startup_score: int | None = None
    effort_score: int | None = None

class OpportunityCreate(BaseModel):
    title: str
    type: str = "freelance"
    description: str | None = None
    source_url: str | None = None
    source_platform: str | None = None
    deadline: date | None = None

class OpportunityList(BaseModel):
    total: int
    items: list[OpportunityOut]
