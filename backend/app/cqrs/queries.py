from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class Query:
    pass


@dataclass(frozen=True)
class GetOpportunityQuery(Query):
    opportunity_id: UUID


@dataclass(frozen=True)
class ListOpportunitiesQuery(Query):
    status: str | None = None
    min_score: float | None = None
    source: str | None = None
    skip: int = 0
    limit: int = 100


@dataclass(frozen=True)
class GetHighScoreOpportunitiesQuery(Query):
    threshold: float = 7.0
    limit: int = 10


@dataclass(frozen=True)
class GetUrgentOpportunitiesQuery(Query):
    """Get urgent opportunities (deadline approaching)."""
    
    days_threshold: int = 3
    limit: int = 10


@dataclass(frozen=True)
class GetSubmissionQuery(Query):
    submission_id: UUID


@dataclass(frozen=True)
class ListSubmissionsQuery(Query):
    status: str | None = None
    opportunity_id: UUID | None = None
    skip: int = 0
    limit: int = 100


@dataclass(frozen=True)
class GetContactQuery(Query):
    contact_id: UUID


@dataclass(frozen=True)
class ListContactsQuery(Query):
    company: str | None = None
    skip: int = 0
    limit: int = 100


@dataclass(frozen=True)
class GetDraftQuery(Query):
    draft_id: UUID


@dataclass(frozen=True)
class ListDraftsQuery(Query):
    status: str | None = "pending"
    skip: int = 0
    limit: int = 100


@dataclass(frozen=True)
class GetWinRateQuery(Query):
    start_date: datetime | None = None
    end_date: datetime | None = None


@dataclass(frozen=True)
class GetDailyCostQuery(Query):
    date: datetime | None = None


@dataclass(frozen=True)
class GetMonthlyCostQuery(Query):
    year: int
    month: int


@dataclass(frozen=True)
class GetCostBreakdownQuery(Query):
    start_date: datetime
    end_date: datetime


@dataclass(frozen=True)
class GetCostForecastQuery(Query):
    period: str = "monthly"


@dataclass(frozen=True)
class GetScraperHealthQuery(Query):
    scraper_name: str


@dataclass(frozen=True)
class ListScrapersQuery(Query):
    include_muted: bool = True


@dataclass(frozen=True)
class GetScraperStatsQuery(Query):
    scraper_name: str
    days: int = 30


@dataclass(frozen=True)
class GetApprovalQuery(Query):
    approval_id: UUID


@dataclass(frozen=True)
class ListPendingApprovalsQuery(Query):
    priority: str | None = None
    limit: int = 10


@dataclass(frozen=True)
class GetApprovalStatsQuery(Query):
    start_date: datetime | None = None
    end_date: datetime | None = None


@dataclass(frozen=True)
class GetDashboardStatsQuery(Query):
    period: str = "week"


@dataclass(frozen=True)
class GetSystemHealthQuery(Query):
    pass
