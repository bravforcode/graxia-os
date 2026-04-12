from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    title: str
    description: Optional[str] = None
    source_url: Optional[str] = None
    source_platform: Optional[str] = None
    deadline: Optional[date] = None
    total_score: Optional[Decimal] = None
    scoring_rationale: Optional[str] = None
    red_flags: Optional[list] = []
    decision: Optional[str] = None
    decision_confidence: Optional[Decimal] = None
    decision_reasoning: Optional[str] = None
    action_priority: Optional[str] = None
    status: Optional[str] = None
    prize_amount: Optional[str] = None
    tags: Optional[list] = []
    is_student_eligible: Optional[bool] = None
    location_type: Optional[str] = None
    fit_summary: Optional[str] = None
    found_at: Optional[datetime] = None
    money_score: Optional[int] = None
    brand_score: Optional[int] = None
    network_score: Optional[int] = None
    startup_score: Optional[int] = None
    effort_score: Optional[int] = None

class OpportunityList(BaseModel):
    total: int
    items: list[OpportunityOut]
