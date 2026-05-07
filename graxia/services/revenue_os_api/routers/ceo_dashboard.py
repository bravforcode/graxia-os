"""
CEO Dashboard API Routes
Executive overview endpoints for Revenue OS v12
"""
from typing import Optional
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db_session
from ....packages.revenue_os.models import (
    Order, Lead, RevenueCampaign, Approval, IncidentEvent, 
    BWCPMessage, OutboxEvent
)
from ....packages.revenue_os.enums import (
    OrderStatus, LeadStatus, CampaignStatus, 
    ApprovalStatus, IncidentSeverity
)
from ....packages.revenue_os.schemas.ceo_schemas import (
    CEODashboardSummary,
    RevenueMetrics,
    CampaignPerformance,
    ApprovalQueue,
    CriticalIncidents,
    AgentActivity,
)
from ..dependencies import require_admin_api_key

router = APIRouter(prefix="/ceo-dashboard", tags=["CEO Dashboard"])


@router.get(
    "/summary",
    response_model=CEODashboardSummary,
    summary="CEO dashboard summary",
    description="High-level executive overview of Revenue OS",
)
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Get CEO dashboard summary."""
    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # Revenue metrics
    revenue_stats = await _get_revenue_metrics(db, today, week_ago, month_ago)
    
    # Campaign performance
    campaign_stats = await _get_campaign_stats(db)
    
    # Approval queue
    approval_stats = await _get_approval_stats(db)
    
    # Critical incidents
    incident_stats = await _get_incident_stats(db)
    
    # Agent activity
    agent_stats = await _get_agent_stats(db)
    
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "revenue": revenue_stats,
        "campaigns": campaign_stats,
        "approvals": approval_stats,
        "incidents": incident_stats,
        "agent_activity": agent_stats,
    }


async def _get_revenue_metrics(db: AsyncSession, today, week_ago, month_ago):
    """Get revenue metrics for dashboard."""
    # Today's revenue
    today_result = await db.execute(
        select(func.sum(Order.amount_cents))
        .where(
            and_(
                Order.status.in_([OrderStatus.FULFILLED, OrderStatus.PROCESSING]),
                func.date(Order.created_at) == today,
            )
        )
    )
    today_revenue = (today_result.scalar() or 0) / 100
    
    # This week's revenue
    week_result = await db.execute(
        select(func.sum(Order.amount_cents))
        .where(
            and_(
                Order.status.in_([OrderStatus.FULFILLED, OrderStatus.PROCESSING]),
                func.date(Order.created_at) >= week_ago,
            )
        )
    )
    week_revenue = (week_result.scalar() or 0) / 100
    
    # This month's revenue
    month_result = await db.execute(
        select(func.sum(Order.amount_cents))
        .where(
            and_(
                Order.status.in_([OrderStatus.FULFILLED, OrderStatus.PROCESSING]),
                func.date(Order.created_at) >= month_ago,
            )
        )
    )
    month_revenue = (month_result.scalar() or 0) / 100
    
    # Pending orders
    pending_result = await db.execute(
        select(func.count(Order.id))
        .where(Order.status == OrderStatus.PENDING)
    )
    pending_orders = pending_result.scalar() or 0
    
    # Refunds today
    refund_result = await db.execute(
        select(func.count(Order.id))
        .where(
            and_(
                Order.status == OrderStatus.REFUNDED,
                func.date(Order.updated_at) == today,
            )
        )
    )
    refunds_today = refund_result.scalar() or 0
    
    return {
        "today_cents": int(today_revenue * 100),
        "week_cents": int(week_revenue * 100),
        "month_cents": int(month_revenue * 100),
        "pending_orders": pending_orders,
        "refunds_today": refunds_today,
    }


async def _get_campaign_stats(db: AsyncSession):
    """Get campaign statistics."""
    # Active campaigns
    active_result = await db.execute(
        select(func.count(RevenueCampaign.id))
        .where(RevenueCampaign.status == CampaignStatus.ACTIVE)
    )
    active = active_result.scalar() or 0
    
    # Paused campaigns
    paused_result = await db.execute(
        select(func.count(RevenueCampaign.id))
        .where(RevenueCampaign.status == CampaignStatus.PAUSED)
    )
    paused = paused_result.scalar() or 0
    
    # Over budget campaigns
    over_budget_result = await db.execute(
        select(func.count(RevenueCampaign.id))
        .where(
            and_(
                RevenueCampaign.status == CampaignStatus.ACTIVE,
                RevenueCampaign.spent_cents > RevenueCampaign.budget_cents,
            )
        )
    )
    over_budget = over_budget_result.scalar() or 0
    
    # Campaigns needing approval
    needs_approval = await db.execute(
        select(func.count(RevenueCampaign.id))
        .where(RevenueCampaign.status == CampaignStatus.DRAFT)
    )
    draft = needs_approval.scalar() or 0
    
    return {
        "active": active,
        "paused": paused,
        "over_budget": over_budget,
        "needs_approval": draft,
    }


async def _get_approval_stats(db: AsyncSession):
    """Get approval queue statistics."""
    # Pending approvals
    pending_result = await db.execute(
        select(func.count(Approval.id))
        .where(Approval.status == ApprovalStatus.PENDING)
    )
    pending = pending_result.scalar() or 0
    
    # High priority pending
    high_priority = await db.execute(
        select(func.count(Approval.id))
        .where(
            and_(
                Approval.status == ApprovalStatus.PENDING,
                Approval.priority.in_(["high", "urgent"]),
            )
        )
    )
    high = high_priority.scalar() or 0
    
    # Expiring soon (within 24h)
    tomorrow = datetime.utcnow() + timedelta(hours=24)
    expiring = await db.execute(
        select(func.count(Approval.id))
        .where(
            and_(
                Approval.status == ApprovalStatus.PENDING,
                Approval.expires_at <= tomorrow,
            )
        )
    )
    expiring_soon = expiring.scalar() or 0
    
    # Approved today
    today = datetime.utcnow().date()
    approved_today = await db.execute(
        select(func.count(Approval.id))
        .where(
            and_(
                Approval.status == ApprovalStatus.APPROVED,
                func.date(Approval.updated_at) == today,
            )
        )
    )
    approved = approved_today.scalar() or 0
    
    return {
        "pending_total": pending,
        "high_priority": high,
        "expiring_soon": expiring_soon,
        "approved_today": approved,
    }


async def _get_incident_stats(db: AsyncSession):
    """Get incident statistics."""
    # Open critical incidents
    critical_result = await db.execute(
        select(func.count(IncidentEvent.id))
        .where(
            and_(
                IncidentEvent.severity == IncidentSeverity.CRITICAL,
                IncidentEvent.resolved_at.is_(None),
            )
        )
    )
    critical = critical_result.scalar() or 0
    
    # Open high incidents
    high_result = await db.execute(
        select(func.count(IncidentEvent.id))
        .where(
            and_(
                IncidentEvent.severity == IncidentSeverity.HIGH,
                IncidentEvent.resolved_at.is_(None),
            )
        )
    )
    high = high_result.scalar() or 0
    
    # Total open incidents
    open_result = await db.execute(
        select(func.count(IncidentEvent.id))
        .where(IncidentEvent.resolved_at.is_(None))
    )
    total_open = open_result.scalar() or 0
    
    # Resolved today
    today = datetime.utcnow().date()
    resolved_today = await db.execute(
        select(func.count(IncidentEvent.id))
        .where(
            and_(
                IncidentEvent.resolved_at.isnot(None),
                func.date(IncidentEvent.resolved_at) == today,
            )
        )
    )
    resolved = resolved_today.scalar() or 0
    
    return {
        "critical_open": critical,
        "high_open": high,
        "total_open": total_open,
        "resolved_today": resolved,
    }


async def _get_agent_stats(db: AsyncSession):
    """Get agent activity statistics."""
    # Undelivered BWCP messages
    pending_result = await db.execute(
        select(func.count(BWCPMessage.id))
        .where(BWCPMessage.delivered == False)
    )
    pending_messages = pending_result.scalar() or 0
    
    # Unprocessed outbox events
    outbox_result = await db.execute(
        select(func.count(OutboxEvent.id))
        .where(OutboxEvent.processed == False)
    )
    pending_events = outbox_result.scalar() or 0
    
    # Failed outbox events (retry >= 3)
    failed_result = await db.execute(
        select(func.count(OutboxEvent.id))
        .where(OutboxEvent.retry_count >= 3)
    )
    failed_events = failed_result.scalar() or 0
    
    # New leads today
    today = datetime.utcnow().date()
    leads_today = await db.execute(
        select(func.count(Lead.id))
        .where(func.date(Lead.created_at) == today)
    )
    new_leads = leads_today.scalar() or 0
    
    return {
        "pending_bwcp_messages": pending_messages,
        "pending_outbox_events": pending_events,
        "failed_outbox_events": failed_events,
        "new_leads_today": new_leads,
    }


@router.get(
    "/revenue",
    response_model=RevenueMetrics,
    summary="Revenue metrics",
    description="Detailed revenue breakdown",
)
async def get_revenue_metrics(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Get detailed revenue metrics."""
    start_date = datetime.utcnow().date() - timedelta(days=days)
    
    # Daily revenue breakdown
    daily_result = await db.execute(
        select(
            func.date(Order.created_at).label("date"),
            func.sum(Order.amount_cents).label("revenue"),
            func.count(Order.id).label("orders"),
        )
        .where(
            and_(
                Order.status.in_([OrderStatus.FULFILLED, OrderStatus.PROCESSING]),
                func.date(Order.created_at) >= start_date,
            )
        )
        .group_by(func.date(Order.created_at))
        .order_by(func.date(Order.created_at))
    )
    daily = [
        {
            "date": str(row.date),
            "revenue_cents": int(row.revenue or 0),
            "orders": row.orders,
        }
        for row in daily_result.all()
    ]
    
    # By platform
    platform_result = await db.execute(
        select(
            Order.platform,
            func.sum(Order.amount_cents).label("revenue"),
            func.count(Order.id).label("orders"),
        )
        .where(
            and_(
                Order.status.in_([OrderStatus.FULFILLED, OrderStatus.PROCESSING]),
                func.date(Order.created_at) >= start_date,
            )
        )
        .group_by(Order.platform)
    )
    by_platform = {
        row.platform: {
            "revenue_cents": int(row.revenue or 0),
            "orders": row.orders,
        }
        for row in platform_result.all()
    }
    
    return {
        "period_days": days,
        "daily_breakdown": daily,
        "by_platform": by_platform,
    }


@router.get(
    "/campaigns",
    response_model=CampaignPerformance,
    summary="Campaign performance",
    description="Campaign effectiveness metrics",
)
async def get_campaign_performance(
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Get campaign performance metrics."""
    # Top performing campaigns by revenue
    top_result = await db.execute(
        select(RevenueCampaign)
        .where(RevenueCampaign.status == CampaignStatus.ACTIVE)
        .order_by(desc(RevenueCampaign.current_revenue_cents))
        .limit(5)
    )
    top_campaigns = top_result.scalars().all()
    
    # Campaigns needing attention (over budget or no recent leads)
    week_ago = datetime.utcnow() - timedelta(days=7)
    attention_result = await db.execute(
        select(RevenueCampaign)
        .where(
            and_(
                RevenueCampaign.status == CampaignStatus.ACTIVE,
                RevenueCampaign.spent_cents > RevenueCampaign.budget_cents * 0.8,  # >80% budget
            )
        )
        .order_by(desc(RevenueCampaign.spent_cents))
        .limit(5)
    )
    attention_needed = attention_result.scalars().all()
    
    return {
        "top_performers": [
            {
                "id": str(c.id),
                "name": c.name,
                "revenue_cents": c.current_revenue_cents,
                "spent_cents": c.spent_cents,
                "roas": c.current_revenue_cents / max(c.spent_cents, 1),
            }
            for c in top_campaigns
        ],
        "needs_attention": [
            {
                "id": str(c.id),
                "name": c.name,
                "budget_cents": c.budget_cents,
                "spent_cents": c.spent_cents,
                "spend_percentage": (c.spent_cents / max(c.budget_cents, 1)) * 100,
            }
            for c in attention_needed
        ],
    }


@router.get(
    "/approvals",
    response_model=ApprovalQueue,
    summary="Approval queue",
    description="Pending approvals requiring CEO attention",
)
async def get_approval_queue(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Get pending approvals queue."""
    # Pending approvals ordered by priority and created date
    pending_result = await db.execute(
        select(Approval)
        .where(Approval.status == ApprovalStatus.PENDING)
        .order_by(
            desc(Approval.priority == "urgent"),
            desc(Approval.priority == "high"),
            desc(Approval.created_at),
        )
        .limit(limit)
    )
    pending = pending_result.scalars().all()
    
    return {
        "pending": [
            {
                "id": str(a.id),
                "approval_type": a.approval_type,
                "title": a.title,
                "priority": a.priority,
                "requested_by": a.requested_by,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "expires_at": a.expires_at.isoformat() if a.expires_at else None,
            }
            for a in pending
        ],
        "total_pending": len(pending),
    }


@router.get(
    "/incidents",
    response_model=CriticalIncidents,
    summary="Critical incidents",
    description="Open high/critical incidents",
)
async def get_critical_incidents(
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Get critical and high severity incidents."""
    # Critical incidents
    critical_result = await db.execute(
        select(IncidentEvent)
        .where(
            and_(
                IncidentEvent.severity == IncidentSeverity.CRITICAL,
                IncidentEvent.resolved_at.is_(None),
            )
        )
        .order_by(desc(IncidentEvent.created_at))
    )
    critical = critical_result.scalars().all()
    
    # High incidents
    high_result = await db.execute(
        select(IncidentEvent)
        .where(
            and_(
                IncidentEvent.severity == IncidentSeverity.HIGH,
                IncidentEvent.resolved_at.is_(None),
            )
        )
        .order_by(desc(IncidentEvent.created_at))
        .limit(10)
    )
    high = high_result.scalars().all()
    
    return {
        "critical": [
            {
                "id": str(i.id),
                "title": i.title,
                "description": i.description,
                "severity": i.severity.value,
                "created_at": i.created_at.isoformat() if i.created_at else None,
                "related_campaign_id": str(i.campaign_id) if i.campaign_id else None,
            }
            for i in critical
        ],
        "high": [
            {
                "id": str(i.id),
                "title": i.title,
                "severity": i.severity.value,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in high
        ],
    }
