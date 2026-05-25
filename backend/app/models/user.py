"""User model for authentication."""
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class User(Base, TenantMixin):
    """User model for authentication and authorization."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    totp_secret: Mapped[str | None] = mapped_column(String(128))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )
    provider: Mapped[str | None] = mapped_column(String(50))
    provider_id: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def onboarding_complete(self) -> bool:
        """Check if user has completed onboarding."""
        return self.onboarding_completed_at is not None

    # Relationships
    from sqlalchemy.orm import relationship
    organization = relationship("Organization", back_populates="users")

    def __repr__(self) -> str:
        return f"<User {self.email}>"
