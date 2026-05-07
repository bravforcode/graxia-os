"""
Analytics & Reporting — Features 41-55
Comprehensive analytics, dashboards, and reporting system
"""

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
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
# FEATURE 41-45: ANALYTICS DASHBOARDS & METRICS
# ═══════════════════════════════════════════════════════════════════════════════


class AnalyticsDashboard(Base):
    """Custom analytics dashboards."""

    __tablename__ = "analytics_dashboards"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    dashboard_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Owner
    owner_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)

    # Configuration
    layout: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict
    )  # {widgets: [{type, position, config}]}
    time_range_default: Mapped[str] = mapped_column(String(20), default="7d")  # 1d, 7d, 30d, 90d
    refresh_interval_seconds: Mapped[int | None] = mapped_column(Integer)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class AnalyticsWidget(Base):
    """Individual widgets for dashboards."""

    __tablename__ = "analytics_widgets"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    widget_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    dashboard_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("analytics_dashboards.id"), nullable=False, index=True
    )

    # Widget configuration
    widget_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # chart, metric, table, gauge, list
    title: Mapped[str] = mapped_column(String(255))

    # Data source
    data_source: Mapped[str] = mapped_column(String(100))  # skills, agents, executions, etc.
    metric_name: Mapped[str] = mapped_column(String(100))  # count, avg, sum, etc.

    # Query configuration
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    group_by: Mapped[str | None] = mapped_column(String(100))
    time_granularity: Mapped[str | None] = mapped_column(String(20))  # hour, day, week, month

    # Visual configuration
    chart_type: Mapped[str | None] = mapped_column(String(50))  # line, bar, pie, area
    color_scheme: Mapped[str | None] = mapped_column(String(50))

    # Position
    position_x: Mapped[int] = mapped_column(Integer, default=0)
    position_y: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int] = mapped_column(Integer, default=6)
    height: Mapped[int] = mapped_column(Integer, default=4)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class AnalyticsMetric(Base):
    """Pre-computed analytics metrics."""

    __tablename__ = "analytics_metrics"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    metric_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Dimension
    dimension: Mapped[str] = mapped_column(String(100), index=True)  # skill, agent, time, category
    dimension_value: Mapped[str] = mapped_column(String(255), index=True)

    # Time period
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_type: Mapped[str] = mapped_column(String(20), default="day")  # hour, day, week, month

    # Values
    value_numeric: Mapped[float | None] = mapped_column(Numeric(20, 6))
    value_count: Mapped[int | None] = mapped_column(Integer)
    value_text: Mapped[str | None] = mapped_column(Text)

    # Extra metadata (renamed to avoid SQLAlchemy reserved word)
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    __table_args__ = (Index("ix_metric_dimension_time", "metric_key", "dimension", "period_start"),)


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 46-50: SKILL ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════


class SkillUsageAnalytics(Base):
    """Usage analytics for individual skills."""

    __tablename__ = "skill_usage_analytics"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    skill_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=False, index=True
    )

    # Time period
    period_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    period_type: Mapped[str] = mapped_column(String(20), default="day")

    # Usage metrics
    total_invocations: Mapped[int] = mapped_column(Integer, default=0)
    unique_agents: Mapped[int] = mapped_column(Integer, default=0)
    unique_sessions: Mapped[int] = mapped_column(Integer, default=0)

    # Performance metrics
    avg_execution_time_ms: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    min_execution_time_ms: Mapped[int | None] = mapped_column(Integer)
    max_execution_time_ms: Mapped[int | None] = mapped_column(Integer)

    # Success metrics
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0)

    # Input/Output metrics
    avg_input_tokens: Mapped[int | None] = mapped_column(Integer)
    avg_output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens_consumed: Mapped[int] = mapped_column(Integer, default=0)

    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (Index("ix_skill_analytics_date", "skill_id", "period_date", unique=True),)


class SkillPerformanceTrend(Base):
    """Performance trends for skills over time."""

    __tablename__ = "skill_performance_trends"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    skill_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("skillsmp_skills.id"), nullable=False, index=True
    )

    # Trend analysis
    trend_type: Mapped[str] = mapped_column(String(50), index=True)  # usage, quality, performance
    trend_direction: Mapped[str] = mapped_column(String(20))  # improving, stable, declining

    # Metrics
    current_value: Mapped[float] = mapped_column(Numeric(10, 4))
    previous_value: Mapped[float] = mapped_column(Numeric(10, 4))
    change_percent: Mapped[float] = mapped_column(Numeric(10, 4))

    # Analysis period
    analysis_window_days: Mapped[int] = mapped_column(Integer, default=30)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class AgentPerformanceAnalytics(Base):
    """Performance analytics for agents."""

    __tablename__ = "agent_performance_analytics"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    agent_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )

    # Time period
    period_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    period_type: Mapped[str] = mapped_column(String(20), default="day")

    # Activity metrics
    skills_created: Mapped[int] = mapped_column(Integer, default=0)
    skills_updated: Mapped[int] = mapped_column(Integer, default=0)
    chains_created: Mapped[int] = mapped_column(Integer, default=0)
    collaborations_joined: Mapped[int] = mapped_column(Integer, default=0)

    # Execution metrics
    total_executions: Mapped[int] = mapped_column(Integer, default=0)
    successful_executions: Mapped[int] = mapped_column(Integer, default=0)
    failed_executions: Mapped[int] = mapped_column(Integer, default=0)

    # Contribution metrics
    code_contributions: Mapped[int] = mapped_column(Integer, default=0)
    reviews_given: Mapped[int] = mapped_column(Integer, default=0)
    mentorship_sessions: Mapped[int] = mapped_column(Integer, default=0)

    # Quality metrics
    average_skill_rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0)

    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 51-55: REPORTING & EXPORT
# ═══════════════════════════════════════════════════════════════════════════════


class AnalyticsReport(Base):
    """Generated analytics reports."""

    __tablename__ = "analytics_reports"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    report_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Report configuration
    report_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # usage, performance, financial, custom

    # Filters
    date_range_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    date_range_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Generated content
    content_summary: Mapped[str | None] = mapped_column(Text)
    content_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    charts_data: Mapped[list[dict]] = mapped_column(JSONB, default=list)

    # Export
    export_format: Mapped[str] = mapped_column(String(20), default="json")  # json, csv, pdf
    export_url: Mapped[str | None] = mapped_column(String(500))

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="generating"
    )  # generating, ready, failed

    # Owner
    generated_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ScheduledReport(Base):
    """Scheduled recurring reports."""

    __tablename__ = "scheduled_reports"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    schedule_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Report template
    report_type: Mapped[str] = mapped_column(String(50))
    report_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Schedule
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)  # daily, weekly, monthly
    day_of_week: Mapped[int | None] = mapped_column(Integer)  # 0-6 for weekly
    day_of_month: Mapped[int | None] = mapped_column(Integer)  # 1-31 for monthly
    time_of_day: Mapped[str] = mapped_column(String(5), default="09:00")  # HH:MM
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    # Recipients
    recipient_agent_ids: Mapped[list[UUIDType]] = mapped_column(JSONB, default=list)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class AnalyticsAlert(Base):
    """Alerts based on analytics thresholds."""

    __tablename__ = "analytics_alerts"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    alert_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Alert condition
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    condition_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # above, below, equals, change_percent
    threshold_value: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)

    # Scope
    scope_type: Mapped[str] = mapped_column(String(50), default="global")  # skill, agent, global
    scope_id: Mapped[UUIDType | None] = mapped_column(SQLUUID(as_uuid=True), nullable=True)

    # Notification
    notification_channels: Mapped[list[str]] = mapped_column(
        JSONB, default=list
    )  # email, slack, webhook
    severity: Mapped[str] = mapped_column(String(20), default="warning")  # info, warning, critical

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trigger_count: Mapped[int] = mapped_column(Integer, default=0)

    created_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class AnalyticsAlertTrigger(Base):
    """Record of triggered alerts."""

    __tablename__ = "analytics_alert_triggers"

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    alert_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("analytics_alerts.id"), nullable=False, index=True
    )

    # Trigger details
    triggered_value: Mapped[float] = mapped_column(Numeric(20, 6))
    threshold_value: Mapped[float] = mapped_column(Numeric(20, 6))

    # Context
    context_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Notification status
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_channels_sent: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # Acknowledgment
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by_agent_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
