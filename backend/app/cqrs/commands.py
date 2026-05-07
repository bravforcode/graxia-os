from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class Command:
    pass


@dataclass(frozen=True)
class CreateOpportunityCommand(Command):
    title: str
    source: str | None = None
    url: str | None = None
    description: str | None = None
    deadline: datetime | None = None
    budget: float | None = None


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
    opportunity_id: UUID | None = None
    contact_id: UUID | None = None
    type: str | None = None
    title: str | None = None
    content: str | None = None
    subject_line: str | None = None
    proposed_value: float | None = None
    currency: str = "THB"
    proposal_text: str | None = None
    created_by: str | None = None


@dataclass(frozen=True)
class MarkSubmissionWonCommand(Command):
    submission_id: UUID
    actual_value: float = 0.0
    value_usd: float = 0.0
    won_at: datetime | None = None


@dataclass(frozen=True)
class MarkSubmissionLostCommand(Command):
    submission_id: UUID
    lost_reason: str = "unknown"
    reason: str | None = None
    lost_at: datetime | None = None


@dataclass(frozen=True)
class CreateContactCommand(Command):
    name: str
    email: str | None = None
    company: str | None = None
    role: str | None = None
    linkedin_url: str | None = None
    twitter_handle: str | None = None
    telegram_handle: str | None = None
    notes: str | None = None


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
    reason: str | None = None


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
    metadata: dict | None = None
