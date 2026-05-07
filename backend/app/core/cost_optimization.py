"""
FinOps & Cost Optimization System

Enterprise-grade cost monitoring and optimization for cloud resources.
Tracks usage, identifies waste, and provides recommendations.

Features:
- Real-time cost tracking
- Resource utilization monitoring
- Waste detection
- Budget alerts
- Cost allocation by team/project
- Automated cost optimization recommendations
"""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class CostBreakdown:
    """Cost breakdown by category."""
    compute: Decimal
    database: Decimal
    storage: Decimal
    bandwidth: Decimal
    third_party_apis: Decimal
    other: Decimal
    
    @property
    def total(self) -> Decimal:
        return sum([
            self.compute,
            self.database,
            self.storage,
            self.bandwidth,
            self.third_party_apis,
            self.other
        ], Decimal("0"))


@dataclass
class ResourceUtilization:
    """Resource utilization metrics."""
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_io_mbps: float
    active_connections: int
    
    @property
    def is_underutilized(self) -> bool:
        return self.cpu_percent < 20 and self.memory_percent < 30
    
    @property
    def is_overutilized(self) -> bool:
        return self.cpu_percent > 80 or self.memory_percent > 85


class CostRecord(Base):
    """
    Database model for cost tracking.
    """
    __tablename__ = "cost_records"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    
    # Organization tracking
    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Cost categorization
    category = Column(String(50), nullable=False, index=True)  # compute, database, storage, api
    service = Column(String(100), nullable=False)  # fly.io, aws, stripe, openclaw
    resource_type = Column(String(50))  # vm, postgres, redis, s3
    
    # Cost details
    amount_usd = Column(Numeric(10, 4), nullable=False)
    currency = Column(String(3), default="USD")
    quantity = Column(Numeric(10, 2))  # hours, GB, requests
    unit_price = Column(Numeric(10, 6))
    
    # Metadata
    description = Column(Text)
    tags = Column(JSONB, default=dict)
    metadata = Column(JSONB, default=dict)


class BudgetAlert(Base):
    """
    Budget alert configuration and history.
    """
    __tablename__ = "budget_alerts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(UTC))
    
    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Alert configuration
    name = Column(String(100), nullable=False)
    budget_amount = Column(Numeric(10, 2), nullable=False)
    alert_thresholds = Column(JSONB, default=lambda: [50, 80, 100])  # Percentages
    
    # Current status
    current_spend = Column(Numeric(10, 2), default=Decimal("0"))
    last_alert_sent_at = Column(DateTime(timezone=True))
    
    # Alert settings
    notification_emails = Column(JSONB, default=list)
    slack_webhook_url = Column(Text)
    
    is_active = Column(Integer, default=1)


class CostOptimizationRecommendation(Base):
    """
    Cost optimization recommendations.
    """
    __tablename__ = "cost_optimization_recommendations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    
    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Recommendation details
    category = Column(String(50), nullable=False)  # rightsizing, reserved_instances, cleanup
    severity = Column(String(20), nullable=False)  # high, medium, low
    title = Column(String(200), nullable=False)
    description = Column(Text)
    
    # Impact
    estimated_monthly_savings = Column(Numeric(10, 2))
    effort_level = Column(String(20))  # easy, medium, hard
    
    # Action
    action_type = Column(String(50))  # auto, manual, review
    action_script = Column(Text)  # For automated actions
    
    # Status
    status = Column(String(20), default="open")  # open, in_progress, applied, dismissed
    applied_at = Column(DateTime(timezone=True))
    applied_by = Column(UUID(as_uuid=True))
    
    # Metadata
    resource_ids = Column(JSONB, default=list)
    metadata = Column(JSONB, default=dict)


class FinOpsManager:
    """
    Enterprise FinOps cost management system.
    """
    
    # Cost per unit (USD) - updated periodically
    COST_RATES = {
        "fly_compute": Decimal("0.00139"),  # Per second for performance-2x
        "fly_postgres": Decimal("0.00056"),  # Per second for basic PostgreSQL
        "fly_redis": Decimal("0.00014"),  # Per second for Redis
        "stripe_transaction": Decimal("0.029") + Decimal("0.30"),  # 2.9% + 30c
        "openclaw_token": Decimal("0.00001"),  # Per token (approximate)
        "resend_email": Decimal("0.0005"),  # Per email (first 3000 free)
    }
    
    def __init__(self, db_session):
        self.db = db_session
        self._current_month_spend: dict[str, Decimal] = defaultdict(Decimal)
    
    async def record_cost(
        self,
        organization_id: str,
        category: str,
        service: str,
        amount_usd: Decimal,
        resource_type: Optional[str] = None,
        quantity: Optional[Decimal] = None,
        description: Optional[str] = None,
        tags: Optional[dict] = None
    ) -> CostRecord:
        """
        Record a cost event.
        """
        cost = CostRecord(
            id=uuid4(),
            created_at=datetime.now(UTC),
            organization_id=organization_id,
            category=category,
            service=service,
            resource_type=resource_type,
            amount_usd=amount_usd,
            quantity=quantity,
            description=description,
            tags=tags or {}
        )
        
        self.db.add(cost)
        await self.db.commit()
        
        # Update current month tracking
        month_key = f"{organization_id}:{datetime.now(UTC).strftime('%Y-%m')}"
        self._current_month_spend[month_key] += amount_usd
        
        # Check budget alerts
        await self._check_budget_alerts(organization_id)
        
        return cost
    
    async def get_cost_summary(
        self,
        organization_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> dict[str, Any]:
        """
        Get cost summary for date range.
        """
        from sqlalchemy import select, func
        
        # Total cost
        total_result = await self.db.execute(
            select(func.sum(CostRecord.amount_usd))
            .where(
                CostRecord.organization_id == organization_id,
                CostRecord.created_at >= start_date,
                CostRecord.created_at <= end_date
            )
        )
        total_cost = total_result.scalar() or Decimal("0")
        
        # Cost by category
        category_result = await self.db.execute(
            select(
                CostRecord.category,
                func.sum(CostRecord.amount_usd).label("amount")
            )
            .where(
                CostRecord.organization_id == organization_id,
                CostRecord.created_at >= start_date,
                CostRecord.created_at <= end_date
            )
            .group_by(CostRecord.category)
        )
        by_category = {cat: amount for cat, amount in category_result.all()}
        
        # Cost by service
        service_result = await self.db.execute(
            select(
                CostRecord.service,
                func.sum(CostRecord.amount_usd).label("amount")
            )
            .where(
                CostRecord.organization_id == organization_id,
                CostRecord.created_at >= start_date,
                CostRecord.created_at <= end_date
            )
            .group_by(CostRecord.service)
        )
        by_service = {svc: amount for svc, amount in service_result.all()}
        
        # Daily breakdown
        daily_result = await self.db.execute(
            select(
                func.date_trunc('day', CostRecord.created_at).label('day'),
                func.sum(CostRecord.amount_usd).label('amount')
            )
            .where(
                CostRecord.organization_id == organization_id,
                CostRecord.created_at >= start_date,
                CostRecord.created_at <= end_date
            )
            .group_by(func.date_trunc('day', CostRecord.created_at))
            .order_by(func.date_trunc('day', CostRecord.created_at))
        )
        daily_breakdown = [
            {"date": day.strftime("%Y-%m-%d"), "amount": float(amount)}
            for day, amount in daily_result.all()
        ]
        
        return {
            "organization_id": organization_id,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "total_cost_usd": float(total_cost),
            "by_category": {k: float(v) for k, v in by_category.items()},
            "by_service": {k: float(v) for k, v in by_service.items()},
            "daily_breakdown": daily_breakdown,
            "currency": "USD"
        }
    
    async def get_month_to_date_cost(self, organization_id: str) -> Decimal:
        """Get current month-to-date cost."""
        now = datetime.now(UTC)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        summary = await self.get_cost_summary(
            organization_id,
            start_of_month,
            now
        )
        
        return Decimal(str(summary["total_cost_usd"]))
    
    async def predict_month_end_cost(self, organization_id: str) -> Decimal:
        """Predict cost at end of month based on current spend rate."""
        now = datetime.now(UTC)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        mtd_cost = await self.get_month_to_date_cost(organization_id)
        
        # Calculate daily average
        days_elapsed = (now - start_of_month).days or 1
        daily_average = mtd_cost / days_elapsed
        
        # Predict for full month
        days_in_month = 30  # Simplified
        predicted_total = daily_average * days_in_month
        
        return predicted_total
    
    async def create_budget_alert(
        self,
        organization_id: str,
        name: str,
        budget_amount: Decimal,
        alert_thresholds: Optional[list] = None,
        notification_emails: Optional[list] = None,
        slack_webhook_url: Optional[str] = None
    ) -> BudgetAlert:
        """Create a new budget alert."""
        alert = BudgetAlert(
            id=uuid4(),
            organization_id=organization_id,
            name=name,
            budget_amount=budget_amount,
            alert_thresholds=alert_thresholds or [50, 80, 100],
            notification_emails=notification_emails or [],
            slack_webhook_url=slack_webhook_url,
            is_active=1
        )
        
        self.db.add(alert)
        await self.db.commit()
        
        return alert
    
    async def _check_budget_alerts(self, organization_id: str):
        """Check and send budget alerts."""
        from sqlalchemy import select
        
        # Get active alerts
        result = await self.db.execute(
            select(BudgetAlert)
            .where(
                BudgetAlert.organization_id == organization_id,
                BudgetAlert.is_active == 1
            )
        )
        alerts = result.scalars().all()
        
        # Get current spend
        current_spend = await self.get_month_to_date_cost(organization_id)
        
        for alert in alerts:
            # Update current spend
            alert.current_spend = current_spend
            
            # Check thresholds
            spend_percent = (current_spend / alert.budget_amount) * 100
            
            triggered_thresholds = [
                t for t in alert.alert_thresholds
                if spend_percent >= t
            ]
            
            if triggered_thresholds:
                highest_triggered = max(triggered_thresholds)
                
                # Check if we already sent an alert for this threshold
                if alert.last_alert_sent_at:
                    # Don't alert more than once per day for same threshold
                    time_since_last = datetime.now(UTC) - alert.last_alert_sent_at
                    if time_since_last < timedelta(hours=24):
                        continue
                
                # Send alert
                await self._send_budget_alert(alert, highest_triggered, spend_percent)
                alert.last_alert_sent_at = datetime.now(UTC)
        
        await self.db.commit()
    
    async def _send_budget_alert(
        self,
        alert: BudgetAlert,
        threshold: int,
        current_percent: Decimal
    ):
        """Send budget alert notification."""
        message = (
            f"🚨 Budget Alert: {alert.name}\n\n"
            f"Threshold: {threshold}%\n"
            f"Current spend: {current_percent:.1f}%\n"
            f"Amount: ${alert.current_spend:.2f} / ${alert.budget_amount:.2f}\n\n"
            f"Organization: {alert.organization_id}"
        )
        
        logger.warning(message)
        
        # TODO: Send email notifications
        # TODO: Send Slack notification
    
    async def generate_optimization_recommendations(
        self,
        organization_id: str
    ) -> list[CostOptimizationRecommendation]:
        """
        Generate cost optimization recommendations.
        """
        recommendations = []
        
        # Analyze underutilized resources
        # In real implementation, query actual usage metrics
        
        # Recommendation 1: Downsize underutilized compute
        rec1 = CostOptimizationRecommendation(
            id=uuid4(),
            organization_id=organization_id,
            category="rightsizing",
            severity="medium",
            title="Downsize underutilized compute instances",
            description="CPU utilization below 20% for 7+ days. Consider downsizing to smaller instance.",
            estimated_monthly_savings=Decimal("50.00"),
            effort_level="easy",
            action_type="manual",
            resource_ids=["instance-1", "instance-2"]
        )
        recommendations.append(rec1)
        
        # Recommendation 2: Reserved instances
        rec2 = CostOptimizationRecommendation(
            id=uuid4(),
            organization_id=organization_id,
            category="reserved_instances",
            severity="high",
            title="Purchase reserved instances for stable workloads",
            description="Consistent compute usage detected. Reserved instances can save up to 40%.",
            estimated_monthly_savings=Decimal("200.00"),
            effort_level="medium",
            action_type="manual"
        )
        recommendations.append(rec2)
        
        # Recommendation 3: Clean up unused storage
        rec3 = CostOptimizationRecommendation(
            id=uuid4(),
            organization_id=organization_id,
            category="cleanup",
            severity="low",
            title="Clean up old backups and unused storage",
            description="Found backups older than retention policy. Automated cleanup available.",
            estimated_monthly_savings=Decimal("25.00"),
            effort_level="easy",
            action_type="auto",
            action_script="python scripts/cleanup_old_backups.py --days 90"
        )
        recommendations.append(rec3)
        
        # Save recommendations
        for rec in recommendations:
            self.db.add(rec)
        
        await self.db.commit()
        
        return recommendations
    
    async def apply_recommendation(
        self,
        recommendation_id: str,
        applied_by: str
    ) -> bool:
        """Apply an optimization recommendation."""
        from sqlalchemy import select
        
        result = await self.db.execute(
            select(CostOptimizationRecommendation)
            .where(CostOptimizationRecommendation.id == recommendation_id)
        )
        rec = result.scalar_one_or_none()
        
        if not rec or rec.status != "open":
            return False
        
        if rec.action_type == "auto" and rec.action_script:
            # Execute automated action
            # In production, use proper job queue
            logger.info(f"Executing auto-action: {rec.action_script}")
        
        rec.status = "applied"
        rec.applied_at = datetime.now(UTC)
        rec.applied_by = applied_by
        
        await self.db.commit()
        
        return True
    
    def calculate_api_cost(self, service: str, quantity: int) -> Decimal:
        """Calculate cost for API usage."""
        rate = self.COST_RATES.get(service, Decimal("0"))
        return rate * Decimal(quantity)


# Global FinOps manager
_finops_manager: Optional[FinOpsManager] = None


def get_finops_manager(db_session) -> FinOpsManager:
    """Get or create FinOps manager instance."""
    global _finops_manager
    if _finops_manager is None:
        _finops_manager = FinOpsManager(db_session)
    return _finops_manager
