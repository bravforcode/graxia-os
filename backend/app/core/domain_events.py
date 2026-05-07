"""
Domain Events Pattern

Event-driven architecture with strong typing and validation.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


def _serialize_event_value(value: Any) -> Any:
    """Convert value objects and nested containers into JSON-safe payload data."""
    if isinstance(value, dict):
        return {key: _serialize_event_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_event_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        candidate = value.value
        if isinstance(candidate, (int, float, str, bool)):
            return candidate
    return value


@dataclass(frozen=True, kw_only=True)
class DomainEvent(ABC):
    """Base class for all domain events."""
    
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    aggregate_id: str | None = None
    aggregate_type: str | None = None
    version: int = 1
    
    @abstractmethod
    def event_type(self) -> str:
        """Return the event type identifier."""
        pass
    
    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type(),
            "occurred_at": self.occurred_at.isoformat(),
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "version": self.version,
            "data": _serialize_event_value(self._get_data()),
        }
    
    @abstractmethod
    def _get_data(self) -> dict[str, Any]:
        """Get event-specific data."""
        pass


# Opportunity Events
@dataclass(frozen=True)
class OpportunityDiscovered(DomainEvent):
    """New opportunity discovered by scraper."""
    
    opportunity_id: str
    title: str
    source: str
    score: float | None = None
    
    def event_type(self) -> str:
        return "opportunity.discovered"
    
    def _get_data(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "title": self.title,
            "source": self.source,
            "score": self.score
        }


@dataclass(frozen=True)
class OpportunityScored(DomainEvent):
    """Opportunity scored by scorer agent."""
    
    opportunity_id: str
    score: float
    reasoning: str
    action_priority: str | None = None
    
    def event_type(self) -> str:
        return "opportunity.scored"
    
    def _get_data(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "score": self.score,
            "reasoning": self.reasoning,
            "action_priority": self.action_priority,
        }


@dataclass(frozen=True)
class OpportunityApproved(DomainEvent):
    """Opportunity approved for action."""
    
    opportunity_id: str
    approved_by: str
    
    def event_type(self) -> str:
        return "opportunity.approved"
    
    def _get_data(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "approved_by": self.approved_by
        }


# Submission Events
@dataclass(frozen=True)
class SubmissionCreated(DomainEvent):
    """New submission created."""
    
    submission_id: str
    opportunity_id: str
    proposal_text: str
    
    def event_type(self) -> str:
        return "submission.created"
    
    def _get_data(self) -> dict[str, Any]:
        return {
            "submission_id": self.submission_id,
            "opportunity_id": self.opportunity_id,
            "proposal_length": len(self.proposal_text)
        }


@dataclass(frozen=True)
class SubmissionSent(DomainEvent):
    """Submission sent to client."""
    
    submission_id: str
    sent_at: datetime
    
    def event_type(self) -> str:
        return "submission.sent"
    
    def _get_data(self) -> dict[str, Any]:
        return {
            "submission_id": self.submission_id,
            "sent_at": self.sent_at.isoformat()
        }


@dataclass(frozen=True)
class SubmissionWon(DomainEvent):
    """Submission won the opportunity."""
    
    submission_id: str
    value_usd: float
    
    def event_type(self) -> str:
        return "submission.won"
    
    def _get_data(self) -> dict[str, Any]:
        return {
            "submission_id": self.submission_id,
            "value_usd": self.value_usd
        }


@dataclass(frozen=True)
class SubmissionLost(DomainEvent):
    """Submission lost the opportunity."""
    
    submission_id: str
    reason: str | None = None
    
    def event_type(self) -> str:
        return "submission.lost"
    
    def _get_data(self) -> dict[str, Any]:
        return {
            "submission_id": self.submission_id,
            "reason": self.reason
        }


# Cost Events
@dataclass(frozen=True)
class CostIncurred(DomainEvent):
    """Cost incurred from API usage."""
    
    service: str
    amount_usd: float
    operation: str
    
    def event_type(self) -> str:
        return "cost.incurred"
    
    def _get_data(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "amount_usd": self.amount_usd,
            "operation": self.operation
        }


@dataclass(frozen=True)
class BudgetThresholdReached(DomainEvent):
    """Budget threshold reached."""
    
    period: str
    current_usd: float
    limit_usd: float
    percentage: float
    
    def event_type(self) -> str:
        return "cost.budget_threshold_reached"
    
    def _get_data(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "current_usd": self.current_usd,
            "limit_usd": self.limit_usd,
            "percentage": self.percentage
        }


# Scraper Events
@dataclass(frozen=True)
class ScraperExecuted(DomainEvent):
    """Scraper executed successfully."""
    
    scraper_name: str
    results_count: int
    duration_ms: float
    
    def event_type(self) -> str:
        return "scraper.executed"
    
    def _get_data(self) -> dict[str, Any]:
        return {
            "scraper_name": self.scraper_name,
            "results_count": self.results_count,
            "duration_ms": self.duration_ms
        }


@dataclass(frozen=True)
class ScraperFailed(DomainEvent):
    """Scraper execution failed."""
    
    scraper_name: str
    error_message: str
    consecutive_failures: int
    
    def event_type(self) -> str:
        return "scraper.failed"
    
    def _get_data(self) -> dict[str, Any]:
        return {
            "scraper_name": self.scraper_name,
            "error_message": self.error_message,
            "consecutive_failures": self.consecutive_failures
        }


@dataclass(frozen=True)
class ScraperMuted(DomainEvent):
    """Scraper muted due to failures."""

    scraper_name: str
    muted_until: datetime

    def event_type(self) -> str:
        return "scraper.muted"

    def _get_data(self) -> dict[str, Any]:
        return {
            "scraper_name": self.scraper_name,
            "muted_until": self.muted_until.isoformat()
        }


# Vault Events
@dataclass(frozen=True)
class VaultSynced(DomainEvent):
    """Vault changes synced back to database."""

    opportunity_id: str
    old_status: str | None
    new_status: str

    def event_type(self) -> str:
        return "vault.synced"

    def _get_data(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "old_status": self.old_status,
            "new_status": self.new_status
        }


# Event Registry
EVENT_REGISTRY: dict[str, type[DomainEvent]] = {
    "opportunity.discovered": OpportunityDiscovered,
    "opportunity.scored": OpportunityScored,
    "opportunity.approved": OpportunityApproved,
    "submission.created": SubmissionCreated,
    "submission.sent": SubmissionSent,
    "submission.won": SubmissionWon,
    "submission.lost": SubmissionLost,
    "cost.incurred": CostIncurred,
    "cost.budget_threshold_reached": BudgetThresholdReached,
    "scraper.executed": ScraperExecuted,
    "scraper.failed": ScraperFailed,
    "scraper.muted": ScraperMuted,
    "vault.synced": VaultSynced,
}


def get_event_class(event_type: str) -> type[DomainEvent] | None:
    """Get event class by type."""
    return EVENT_REGISTRY.get(event_type)
