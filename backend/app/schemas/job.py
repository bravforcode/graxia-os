from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobPostingCreate(BaseModel):
    title: str
    company: str | None = None
    source_platform: str | None = None
    source_url: str | None = None
    location: str | None = None
    job_type: Literal["job", "freelance"] = "freelance"
    employment_type: str | None = None
    description: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    raw_data: dict[str, Any] = Field(default_factory=dict)
    source_hash: str | None = None
    opportunity_id: UUID | None = None


class JobPostingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    company: str | None = None
    source_platform: str | None = None
    source_url: str | None = None
    location: str | None = None
    job_type: str
    employment_type: str | None = None
    description: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    skill_gap_list: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    match_score: Decimal | None = None
    fit_summary: str | None = None
    status: str | None = None
    follow_up_due: date | None = None
    applied_at: datetime | None = None
    last_scored_at: datetime | None = None
    opportunity_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class JobPostingList(BaseModel):
    total: int
    items: list[JobPostingOut]


class JobStatusUpdate(BaseModel):
    status: Literal[
        "discovered",
        "screened",
        "drafted",
        "approved",
        "applied",
        "interview_scheduled",
        "interviewing",
        "offer_received",
        "negotiating",
        "accepted",
        "rejected",
        "archived",
    ]
    follow_up_due: date | None = None


class JobOpportunitySyncResponse(BaseModel):
    synced: int
