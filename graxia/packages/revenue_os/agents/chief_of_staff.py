"""
graxia/packages/revenue_os/agents/cos.py
Chief of Staff (CoS) Agent — monitors system health and escalates issues.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CampaignStatus, IncidentEvent, IncidentSeverity, RevenueCampaign

logger = logging.getLogger(__name__)


async def escalate_issue(
    db: AsyncSession,
    title: str,
    description: str,
    severity: IncidentSeverity,
    affected_campaign_id: Optional[UUID] = None,
    affected_order_id: Optional[UUID] = None,
) -> IncidentEvent:
    """
    CoS agent logic: Create an incident event and escalate.
    
    HIGH-R3-04: For CRITICAL severity incidents affecting a campaign,
    immediately pause the campaign (don't wait for 15-min polling).
    
    Args:
        db: Database session
        title: Incident title
        description: Incident description
        severity: Incident severity level
        affected_campaign_id: Optional campaign ID affected by this incident
        affected_order_id: Optional order ID affected by this incident
        
    Returns:
        Created IncidentEvent
    """
    logger.warning("CoS Agent escalating issue: [%s] %s", severity.value, title)
    
    incident = IncidentEvent(
        severity=severity.value,
        source_agent="Chief of Staff",
        title=title,
        description=description,
        affected_campaign_id=affected_campaign_id,
        affected_order_id=affected_order_id,
    )
    db.add(incident)
    await db.flush()
    
    # HIGH-R3-04: Immediately pause ACTIVE campaigns for CRITICAL incidents
    if severity == IncidentSeverity.CRITICAL and affected_campaign_id:
        result = await db.execute(
            update(RevenueCampaign)
            .where(
                and_(
                    RevenueCampaign.id == affected_campaign_id,
                    RevenueCampaign.status == CampaignStatus.ACTIVE.value,
                )
            )
            .values(
                status=CampaignStatus.PAUSED.value,
                paused_reason=f"Auto-paused: CRITICAL incident {incident.id}",
            )
            .returning(RevenueCampaign.id)
        )
        paused_campaign = result.scalar_one_or_none()
        if paused_campaign:
            logger.critical(
                "Campaign %s immediately paused due to CRITICAL incident %s",
                affected_campaign_id,
                incident.id,
            )
    
    return incident
