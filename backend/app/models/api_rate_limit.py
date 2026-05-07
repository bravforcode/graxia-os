"""API rate limit model for tracking rate limits per service."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, Integer, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class APIRateLimit(Base):
    """
    API rate limit model for tracking rate limits per service.
    
    Attributes:
        id: Unique identifier
        service_name: Name of service (openclaw, gemini, gmail)
        limit_type: Type of limit (requests_per_minute, tokens_per_day, cost_per_month)
        limit_value: Maximum allowed value
        current_value: Current value
        reset_at: When limit resets
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    
    __tablename__ = "api_rate_limits"
    
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    service_name: Mapped[str] = mapped_column(String(100), nullable=False)
    limit_type: Mapped[str | None] = mapped_column(String(50))
    limit_value: Mapped[int | None] = mapped_column(Integer)
    current_value: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reset_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), 
        default=_utc_now, 
        onupdate=_utc_now
    )
    
    __table_args__ = (
        UniqueConstraint("service_name", "limit_type", name="uq_service_limit_type"),
    )
    
    def __repr__(self) -> str:
        return f"<APIRateLimit(service='{self.service_name}', type='{self.limit_type}', {self.current_value}/{self.limit_value})>"
    
    @property
    def is_exceeded(self) -> bool:
        """Check if rate limit is exceeded."""
        if self.limit_value is None:
            return False
        return self.current_value >= self.limit_value
    
    @property
    def is_near_limit(self, threshold: float = 0.8) -> bool:
        """Check if rate limit is near (default 80%)."""
        if self.limit_value is None:
            return False
        return self.current_value >= (self.limit_value * threshold)
    
    @property
    def remaining(self) -> int:
        """Get remaining capacity."""
        if self.limit_value is None:
            return 0
        return max(0, self.limit_value - self.current_value)
    
    @property
    def usage_percentage(self) -> float:
        """Get usage as percentage."""
        if self.limit_value is None or self.limit_value == 0:
            return 0.0
        return (self.current_value / self.limit_value) * 100
    
    @property
    def needs_reset(self) -> bool:
        """Check if limit needs to be reset."""
        if not self.reset_at:
            return False
        return _utc_now() >= self.reset_at
    
    def increment(self, amount: int = 1) -> None:
        """Increment current value."""
        self.current_value += amount
    
    def reset(self, new_reset_at: datetime | None = None) -> None:
        """Reset current value to 0."""
        self.current_value = 0
        if new_reset_at:
            self.reset_at = new_reset_at
    
    @classmethod
    async def get_or_create(
        cls, 
        session, 
        service_name: str, 
        limit_type: str,
        limit_value: int,
        reset_at: datetime
    ):
        """Get existing rate limit or create new one."""
        result = await session.execute(
            select(cls)
            .where(cls.service_name == service_name)
            .where(cls.limit_type == limit_type)
        )
        rate_limit = result.scalar_one_or_none()
        
        if not rate_limit:
            rate_limit = cls(
                service_name=service_name,
                limit_type=limit_type,
                limit_value=limit_value,
                reset_at=reset_at
            )
            session.add(rate_limit)
            await session.flush()
        
        # Reset if needed
        if rate_limit.needs_reset:
            rate_limit.reset(reset_at)
        
        return rate_limit
    
    @classmethod
    async def check_and_increment(
        cls,
        session,
        service_name: str,
        limit_type: str,
        limit_value: int,
        reset_at: datetime,
        amount: int = 1
    ) -> tuple[bool, "APIRateLimit"]:
        """
        Check if rate limit allows request and increment if so.
        
        Returns:
            (allowed, rate_limit) tuple
        """
        rate_limit = await cls.get_or_create(
            session, service_name, limit_type, limit_value, reset_at
        )
        
        if rate_limit.is_exceeded:
            return False, rate_limit
        
        rate_limit.increment(amount)
        return True, rate_limit
