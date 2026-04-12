"""
Specification Pattern

Reusable business rules for filtering and validation.
"""
from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from datetime import datetime, timezone


T = TypeVar('T')


class Specification(ABC, Generic[T]):
    """Base specification interface."""
    
    @abstractmethod
    def is_satisfied_by(self, candidate: T) -> bool:
        """Check if candidate satisfies the specification."""
        pass
    
    def and_(self, other: 'Specification[T]') -> 'Specification[T]':
        """Combine with AND logic."""
        return AndSpecification(self, other)
    
    def or_(self, other: 'Specification[T]') -> 'Specification[T]':
        """Combine with OR logic."""
        return OrSpecification(self, other)
    
    def not_(self) -> 'Specification[T]':
        """Negate specification."""
        return NotSpecification(self)


class AndSpecification(Specification[T]):
    """AND combination of specifications."""
    
    def __init__(self, left: Specification[T], right: Specification[T]):
        self.left = left
        self.right = right
    
    def is_satisfied_by(self, candidate: T) -> bool:
        return self.left.is_satisfied_by(candidate) and self.right.is_satisfied_by(candidate)


class OrSpecification(Specification[T]):
    """OR combination of specifications."""
    
    def __init__(self, left: Specification[T], right: Specification[T]):
        self.left = left
        self.right = right
    
    def is_satisfied_by(self, candidate: T) -> bool:
        return self.left.is_satisfied_by(candidate) or self.right.is_satisfied_by(candidate)


class NotSpecification(Specification[T]):
    """NOT negation of specification."""
    
    def __init__(self, spec: Specification[T]):
        self.spec = spec
    
    def is_satisfied_by(self, candidate: T) -> bool:
        return not self.spec.is_satisfied_by(candidate)


# Opportunity Specifications
class HighScoreOpportunity(Specification):
    """Opportunity with high score (>= 80)."""
    
    def __init__(self, threshold: float = 80.0):
        self.threshold = threshold
    
    def is_satisfied_by(self, opportunity) -> bool:
        return opportunity.score >= self.threshold if opportunity.score else False


class RecentOpportunity(Specification):
    """Opportunity discovered recently."""
    
    def __init__(self, days: int = 7):
        self.days = days
    
    def is_satisfied_by(self, opportunity) -> bool:
        if not opportunity.discovered_at:
            return False
        age_days = (datetime.now(timezone.utc) - opportunity.discovered_at).days
        return age_days <= self.days


class DeadlineApproaching(Specification):
    """Opportunity with deadline approaching."""
    
    def __init__(self, days: int = 3):
        self.days = days
    
    def is_satisfied_by(self, opportunity) -> bool:
        if not opportunity.deadline:
            return False
        days_until = (opportunity.deadline - datetime.now(timezone.utc)).days
        return 0 <= days_until <= self.days


class HighValueOpportunity(Specification):
    """Opportunity with high budget."""
    
    def __init__(self, min_budget: float = 5000.0):
        self.min_budget = min_budget
    
    def is_satisfied_by(self, opportunity) -> bool:
        return opportunity.budget >= self.min_budget if opportunity.budget else False


# Submission Specifications
class WinningSubmission(Specification):
    """Submission that won."""
    
    def is_satisfied_by(self, submission) -> bool:
        return submission.status == "won"


class RecentSubmission(Specification):
    """Submission sent recently."""
    
    def __init__(self, days: int = 30):
        self.days = days
    
    def is_satisfied_by(self, submission) -> bool:
        if not submission.sent_at:
            return False
        age_days = (datetime.now(timezone.utc) - submission.sent_at).days
        return age_days <= self.days


# Cost Specifications
class OverBudget(Specification):
    """Cost exceeds budget."""
    
    def __init__(self, budget: float):
        self.budget = budget
    
    def is_satisfied_by(self, cost) -> bool:
        return cost.amount_usd > self.budget


class HighCostOperation(Specification):
    """Operation with high cost."""
    
    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
    
    def is_satisfied_by(self, operation) -> bool:
        return operation.cost_usd >= self.threshold


# Scraper Specifications
class HealthyScraper(Specification):
    """Scraper is healthy."""
    
    def is_satisfied_by(self, scraper) -> bool:
        return (
            scraper.status == "success" and
            not scraper.is_muted and
            (scraper.consecutive_failures or 0) < 3
        )


class MutedScraper(Specification):
    """Scraper is muted."""
    
    def is_satisfied_by(self, scraper) -> bool:
        return scraper.is_muted


# Composite Specifications (Examples)
class UrgentOpportunity(Specification):
    """Urgent opportunity (high score + deadline approaching)."""
    
    def __init__(self):
        self.spec = HighScoreOpportunity().and_(DeadlineApproaching())
    
    def is_satisfied_by(self, opportunity) -> bool:
        return self.spec.is_satisfied_by(opportunity)


class PremiumOpportunity(Specification):
    """Premium opportunity (high score + high value)."""
    
    def __init__(self):
        self.spec = HighScoreOpportunity().and_(HighValueOpportunity())
    
    def is_satisfied_by(self, opportunity) -> bool:
        return self.spec.is_satisfied_by(opportunity)
