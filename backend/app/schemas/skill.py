from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SkillProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    normalized_name: str
    category: str
    level: str
    years_experience: Decimal | None = None
    aliases: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    market_demand_score: int | None = None
    source: str
    is_active: bool | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SkillProfileList(BaseModel):
    total: int
    items: list[SkillProfileOut]


class SkillBootstrapResponse(BaseModel):
    inserted: int
    updated: int
    total: int
