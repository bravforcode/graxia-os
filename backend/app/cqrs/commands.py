from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass(frozen=True)
class Command:
    pass


@dataclass(frozen=True)
class CreateOpportunityCommand(Command):
    title: str
    source: str | None = None
    url: str | None = None
    description: Optional[str] = None
    deadline: Optional[datetime] = None
    budget: Optional[float] = None


@dataclass(frozen=True)
class ScoreOpportunityCommand(Command):
    opportunity_id: UUID
    scorer_agent_id: str = "system"


@dataclass(frozen=True)
class ApproveOpportunityCommand(Command):
    opportunity_id: UUID
    approved_by: str = "system"


@dataclass(frozen=True)
class RejectOpportunityCommand(Command):
    opportunity_id: UUID
    rejected_by: str = "system"


@dataclass(frozen=True)
class CreateSubmissionCommand(Command):
    opportunity_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    type: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    subject_line: Optional[str] = None
    proposed_value: Optional[float] = None
    currency: str = "THB"
    proposal_text: Optional[str] = None
    created_by: Optional[str] = None


@dataclass(frozen=True)
class MarkSubmissionWonCommand(Command):
    submission_id: UUID
    actual_value: float = 0.0
    value_usd: float = 0.0
    won_at: Optional[datetime] = None


@dataclass(frozen=True)
class MarkSubmissionLostCommand(Command):
    submission_id: UUID
    lost_reason: str = "unknown"
    reason: Optional[str] = None
    lost_at: Optional[datetime] = None


@dataclass(frozen=True)
class CreateContactCommand(Command):
    name: str
    email: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_handle: Optional[str] = None
    telegram_handle: Optional[str] = None
    notes: Optional[str] = None


@dataclass(frozen=True)
class ApproveDraftCommand(Command):
    draft_id: UUID


@dataclass(frozen=True)
class RejectDraftCommand(Command):
    draft_id: UUID
    reason: str = ""


@dataclass(frozen=True)
class SendSubmissionCommand(Command):
    submission_id: UUID
    sent_by: str


@dataclass(frozen=True)
class RequestApprovalCommand(Command):
    action_type: str
    action_description: str
    action_data: dict
    priority: str = "normal"


@dataclass(frozen=True)
class ApproveActionCommand(Command):
    approval_id: UUID
    approved_by: str


@dataclass(frozen=True)
class RejectActionCommand(Command):
    approval_id: UUID
    rejected_by: str
    reason: Optional[str] = None


@dataclass(frozen=True)
class ExecuteScraperCommand(Command):
    scraper_name: str
    force: bool = False


@dataclass(frozen=True)
class MuteScraperCommand(Command):
    scraper_name: str
    muted_until: datetime


@dataclass(frozen=True)
class UnmuteScraperCommand(Command):
    scraper_name: str


@dataclass(frozen=True)
class TrackCostCommand(Command):
    service: str
    operation: str
    amount_usd: float
    metadata: Optional[dict] = None
