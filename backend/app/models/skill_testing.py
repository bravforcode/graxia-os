"""
Skill Testing, A/B Testing, Rollback, Draft Mode — Features 7-10
Comprehensive testing and quality assurance system
"""

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as SQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 7: SKILL TESTING FRAMEWORK
# ═══════════════════════════════════════════════════════════════════════════════


class SkillTestSuite(Base):
    """
    Test suite for a skill

    Feature 7: Skill Testing Framework
    """

    __tablename__ = "skill_test_suites"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    skill_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=False, index=True
    )

    # Suite metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    test_type: Mapped[str] = mapped_column(
        String(50), default="unit"
    )  # unit, integration, e2e, performance

    # Test cases
    test_cases: Mapped[list[dict]] = mapped_column(
        JSONB, default=list
    )  # [{name, input, expected_output, timeout_ms}]

    # Configuration
    environment_vars: Mapped[dict[str, str] | None] = mapped_column(JSONB, default=dict)
    mock_dependencies: Mapped[list[UUIDType] | None] = mapped_column(
        JSONB, default=list
    )  # Skill IDs to mock

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class SkillTestRun(Base):
    """
    Execution record for a test suite
    """

    __tablename__ = "skill_test_runs"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    suite_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skill_test_suites.id"), nullable=False, index=True
    )
    version_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skill_versions.id"), nullable=True
    )

    # Execution results
    status: Mapped[str] = mapped_column(
        String(20), default="running"
    )  # running, passed, failed, error, timeout

    # Test results
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)

    test_results: Mapped[list[dict]] = mapped_column(
        JSONB, default=list
    )  # [{test_name, status, actual_output, error_message, duration_ms}]

    # Coverage
    code_coverage_percent: Mapped[int | None] = mapped_column(Integer)  # 0-100
    branch_coverage_percent: Mapped[int | None] = mapped_column(Integer)

    # Performance
    total_duration_ms: Mapped[int | None] = mapped_column(Integer)

    # Environment
    executed_in_environment: Mapped[str | None] = mapped_column(
        String(100)
    )  # sandbox, staging, production

    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 8: A/B TESTING
# ═══════════════════════════════════════════════════════════════════════════════


class SkillABTest(Base):
    """
    A/B test configuration and results

    Feature 8: A/B Testing
    """

    __tablename__ = "skill_ab_tests"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Test configuration
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Control (A)
    control_skill_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=False
    )
    control_version_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skill_versions.id"), nullable=False
    )

    # Variant (B)
    variant_skill_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=False
    )
    variant_version_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skill_versions.id"), nullable=False
    )

    # Traffic split
    control_traffic_percentage: Mapped[int] = mapped_column(Integer, default=50)
    variant_traffic_percentage: Mapped[int] = mapped_column(Integer, default=50)

    # Success criteria
    primary_metric: Mapped[str] = mapped_column(String(100), default="success_rate")
    minimum_sample_size: Mapped[int] = mapped_column(Integer, default=1000)
    confidence_level: Mapped[float] = mapped_column(Numeric(3, 2), default=0.95)
    minimum_improvement_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=5.0)

    # Results
    status: Mapped[str] = mapped_column(
        String(20), default="running"
    )  # running, completed, stopped

    control_samples: Mapped[int] = mapped_column(Integer, default=0)
    variant_samples: Mapped[int] = mapped_column(Integer, default=0)

    control_success_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    variant_success_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))

    improvement_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))
    p_value: Mapped[float | None] = mapped_column(Numeric(6, 5))
    is_statistically_significant: Mapped[bool | None] = mapped_column(Boolean)

    # Auto-promotion
    auto_promote_if_winner: Mapped[bool] = mapped_column(Boolean, default=False)
    winner_skill_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=True
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 9: ROLLBACK SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════


class SkillRollback(Base):
    """
    Rollback record for skills

    Feature 9: Rollback System
    """

    __tablename__ = "skill_rollbacks"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Rolled back skill
    skill_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=False, index=True
    )

    # Version info
    from_version_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skill_versions.id"), nullable=False
    )
    from_version_number: Mapped[str] = mapped_column(String(50), nullable=False)

    to_version_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skill_versions.id"), nullable=False
    )
    to_version_number: Mapped[str] = mapped_column(String(50), nullable=False)

    # Rollback reason
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_event: Mapped[str | None] = mapped_column(
        String(100)
    )  # error_rate, manual, automated, api_error

    # Metrics that triggered rollback (if automated)
    error_metrics: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=dict
    )  # {error_rate, error_count, threshold, time_window}

    # Rollback execution
    rollback_type: Mapped[str] = mapped_column(String(50), default="automatic")  # automatic, manual
    executed_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    # Validation after rollback
    post_rollback_validation_passed: Mapped[bool | None] = mapped_column(Boolean)
    post_rollback_error_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))

    # Notes
    notes: Mapped[str | None] = mapped_column(Text)

    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 10: DRAFT MODE
# ═══════════════════════════════════════════════════════════════════════════════


class SkillDraft(Base):
    """
    Draft version of a skill

    Feature 10: Draft Mode
    """

    __tablename__ = "skill_drafts"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Draft identification
    draft_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    # Original skill (if editing existing)
    skill_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=True
    )

    # Draft content
    name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)

    # Draft metadata
    based_on_version_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skill_versions.id"), nullable=True
    )

    # Change tracking
    changes_from_base: Mapped[list[dict] | None] = mapped_column(
        JSONB, default=list
    )  # [{field, old_value, new_value}]

    # Auto-save
    auto_save_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_save_interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    last_auto_save_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auto_save_count: Mapped[int] = mapped_column(Integer, default=0)

    # Draft status
    status: Mapped[str] = mapped_column(
        String(20), default="active"
    )  # active, published, discarded

    # Validation before publish
    pre_publish_validation_passed: Mapped[bool | None] = mapped_column(Boolean)
    pre_publish_issues: Mapped[list[dict] | None] = mapped_column(JSONB, default=list)

    # Authorship
    created_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    # Publishing
    published_version_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skill_versions.id"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
