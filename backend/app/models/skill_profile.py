import uuid
from datetime import datetime
from decimal import Decimal
from uuid import UUID as UUIDType

from sqlalchemy import (
    UUID as SQLUUID,
    Boolean,
    CheckConstraint,
    DateTime,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SkillProfile(Base):
    __tablename__ = "skill_profiles"
    __table_args__ = (
        CheckConstraint(
            "category IN ('technical','soft')",
            name="ck_skill_profile_category",
        ),
        CheckConstraint(
            "level IN ('beginner','intermediate','advanced','expert')",
            name="ck_skill_profile_level",
        ),
        CheckConstraint(
            "source IN ('identity_profile','manual','imported')",
            name="ck_skill_profile_source",
        ),
        UniqueConstraint(
            "category",
            "normalized_name",
            name="uq_skill_profiles_category_normalized_name",
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    level: Mapped[str] = mapped_column(String(30), nullable=False)
    years_experience: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    aliases: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    evidence: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    market_demand_score: Mapped[int | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(30), default="identity_profile")
    is_active: Mapped[bool | None] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
