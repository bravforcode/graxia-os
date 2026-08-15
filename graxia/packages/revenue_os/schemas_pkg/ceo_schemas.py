"""
CEO Dashboard Pydantic Schemas
"""
from typing import Optional, List, Dict, Any
from datetime import datetime

from pydantic import BaseModel


class RevenueMetrics(BaseModel):
    """Schema for revenue metrics."""
    today_cents: int
    week_cents: int
    month_cents: int
    pending_orders: int
    refunds_today: int


class CampaignStats(BaseModel):
    """Schema for campaign statistics."""
    active: int
    paused: int
    over_budget: int
    needs_approval: int


class ApprovalStats(BaseModel):
    """Schema for approval statistics."""
    pending_total: int
    high_priority: int
    expiring_soon: int
    approved_today: int


class IncidentStats(BaseModel):
    """Schema for incident statistics."""
    critical_open: int
    high_open: int
    total_open: int
    resolved_today: int


class AgentStats(BaseModel):
    """Schema for agent activity statistics."""
    pending_bwcp_messages: int
    pending_outbox_events: int
    failed_outbox_events: int
    new_leads_today: int


class CEODashboardSummary(BaseModel):
    """Schema for CEO dashboard summary."""
    generated_at: str
    revenue: RevenueMetrics
    campaigns: CampaignStats
    approvals: ApprovalStats
    incidents: IncidentStats
    agent_activity: AgentStats


class DailyRevenue(BaseModel):
    """Schema for daily revenue breakdown."""
    date: str
    revenue_cents: int
    orders: int


class PlatformRevenue(BaseModel):
    """Schema for platform revenue."""
    revenue_cents: int
    orders: int


class RevenueMetricsDetail(BaseModel):
    """Schema for detailed revenue metrics."""
    period_days: int
    daily_breakdown: List[DailyRevenue]
    by_platform: Dict[str, PlatformRevenue]


class TopCampaign(BaseModel):
    """Schema for top performing campaign."""
    id: str
    name: str
    revenue_cents: int
    spent_cents: int
    roas: float


class AttentionCampaign(BaseModel):
    """Schema for campaign needing attention."""
    id: str
    name: str
    budget_cents: int
    spent_cents: int
    spend_percentage: float


class CampaignPerformance(BaseModel):
    """Schema for campaign performance."""
    top_performers: List[TopCampaign]
    needs_attention: List[AttentionCampaign]


class ApprovalItem(BaseModel):
    """Schema for approval queue item."""
    id: str
    approval_type: str
    title: str
    priority: str
    requested_by: str
    created_at: Optional[str] = None
    expires_at: Optional[str] = None


class ApprovalQueue(BaseModel):
    """Schema for approval queue."""
    pending: List[ApprovalItem]
    total_pending: int


class CriticalIncidentItem(BaseModel):
    """Schema for critical incident."""
    id: str
    title: str
    description: Optional[str] = None
    severity: str
    created_at: Optional[str] = None
    related_campaign_id: Optional[str] = None


class HighIncidentItem(BaseModel):
    """Schema for high severity incident."""
    id: str
    title: str
    severity: str
    created_at: Optional[str] = None


class CriticalIncidents(BaseModel):
    """Schema for critical incidents."""
    critical: List[CriticalIncidentItem]
    high: List[HighIncidentItem]


class AgentActivityDetail(BaseModel):
    """Schema for detailed agent activity."""
    agent_type: str
    messages_sent_today: int
    messages_received_today: int
    avg_response_time_minutes: Optional[float] = None


class AgentActivity(BaseModel):
    """Schema for agent activity."""
    by_agent: List[AgentActivityDetail]
    total_conversations_today: int
