"""
Value Objects Pattern

Immutable, validated value objects for domain modeling.
"""
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime


@dataclass(frozen=True)
class Money:
    """Money value object with currency."""
    
    amount: Decimal
    currency: str = "USD"
    
    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("Money amount cannot be negative")
        if not self.currency:
            raise ValueError("Currency is required")
    
    def __add__(self, other: 'Money') -> 'Money':
        if self.currency != other.currency:
            raise ValueError(f"Cannot add {self.currency} and {other.currency}")
        return Money(self.amount + other.amount, self.currency)
    
    def __sub__(self, other: 'Money') -> 'Money':
        if self.currency != other.currency:
            raise ValueError(f"Cannot subtract {self.currency} and {other.currency}")
        return Money(self.amount - other.amount, self.currency)
    
    def __mul__(self, multiplier: float) -> 'Money':
        return Money(self.amount * Decimal(str(multiplier)), self.currency)
    
    def __str__(self) -> str:
        return f"{self.currency} {self.amount:.2f}"
    
    @classmethod
    def zero(cls, currency: str = "USD") -> 'Money':
        """Create zero money."""
        return cls(Decimal("0"), currency)
    
    @classmethod
    def from_float(cls, amount: float, currency: str = "USD") -> 'Money':
        """Create from float."""
        return cls(Decimal(str(amount)), currency)


@dataclass(frozen=True)
class Score:
    """Score value object (0-100)."""
    
    value: float
    
    def __post_init__(self):
        if not 0 <= self.value <= 100:
            raise ValueError("Score must be between 0 and 100")
    
    def __str__(self) -> str:
        return f"{self.value:.1f}/100"
    
    def is_high(self) -> bool:
        """Check if score is high (>= 80)."""
        return self.value >= 80
    
    def is_medium(self) -> bool:
        """Check if score is medium (50-79)."""
        return 50 <= self.value < 80
    
    def is_low(self) -> bool:
        """Check if score is low (< 50)."""
        return self.value < 50
    
    @classmethod
    def from_percentage(cls, percentage: float) -> 'Score':
        """Create from percentage (0-1)."""
        return cls(percentage * 100)


@dataclass(frozen=True)
class Email:
    """Email address value object."""
    
    address: str
    
    def __post_init__(self):
        if not self.address or "@" not in self.address:
            raise ValueError(f"Invalid email address: {self.address}")
    
    def __str__(self) -> str:
        return self.address
    
    @property
    def domain(self) -> str:
        """Get email domain."""
        return self.address.split("@")[1]
    
    @property
    def local_part(self) -> str:
        """Get local part of email."""
        return self.address.split("@")[0]


@dataclass(frozen=True)
class URL:
    """URL value object."""
    
    value: str
    
    def __post_init__(self):
        if not self.value or not self.value.startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL: {self.value}")
    
    def __str__(self) -> str:
        return self.value
    
    @property
    def domain(self) -> str:
        """Get domain from URL."""
        from urllib.parse import urlparse
        return urlparse(self.value).netloc


@dataclass(frozen=True)
class DateRange:
    """Date range value object."""
    
    start: datetime
    end: datetime
    
    def __post_init__(self):
        if self.start > self.end:
            raise ValueError("Start date must be before end date")
    
    def contains(self, date: datetime) -> bool:
        """Check if date is in range."""
        return self.start <= date <= self.end
    
    def duration_days(self) -> int:
        """Get duration in days."""
        return (self.end - self.start).days
    
    def __str__(self) -> str:
        return f"{self.start.date()} to {self.end.date()}"


@dataclass(frozen=True)
class Percentage:
    """Percentage value object (0-100)."""
    
    value: float
    
    def __post_init__(self):
        if not 0 <= self.value <= 100:
            raise ValueError("Percentage must be between 0 and 100")
    
    def __str__(self) -> str:
        return f"{self.value:.1f}%"
    
    def as_decimal(self) -> float:
        """Get as decimal (0-1)."""
        return self.value / 100
    
    @classmethod
    def from_decimal(cls, decimal: float) -> 'Percentage':
        """Create from decimal (0-1)."""
        return cls(decimal * 100)
    
    @classmethod
    def from_ratio(cls, numerator: float, denominator: float) -> 'Percentage':
        """Create from ratio."""
        if denominator == 0:
            return cls(0)
        return cls((numerator / denominator) * 100)


@dataclass(frozen=True)
class Priority:
    """Priority value object."""
    
    level: str
    
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    
    def __post_init__(self):
        valid = [self.URGENT, self.HIGH, self.NORMAL, self.LOW]
        if self.level not in valid:
            raise ValueError(f"Invalid priority: {self.level}. Must be one of {valid}")
    
    def __str__(self) -> str:
        return self.level
    
    def __lt__(self, other: 'Priority') -> bool:
        """Compare priorities."""
        order = {self.URGENT: 0, self.HIGH: 1, self.NORMAL: 2, self.LOW: 3}
        return order[self.level] < order[other.level]
    
    def is_urgent(self) -> bool:
        return self.level == self.URGENT
    
    def is_high(self) -> bool:
        return self.level == self.HIGH
