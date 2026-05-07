"""
graxia/packages/revenue_os/agents/visionary.py
Visionary Agent — responsible for proposing new Revenue Campaigns.
"""
from __future__ import annotations

import logging
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import RevenueCampaign, CampaignStatus, Approval, ApprovalStatus

logger = logging.getLogger(__name__)

async def propose_campaign(db: AsyncSession, name: str, budget_cents: int, target_revenue_cents: int) -> RevenueCampaign:
    """
    Visionary agent logic: Propose a new campaign.
    Campaigns proposed by Visionary require approval by default.
    """
    logger.info("Visionary Agent proposing campaign: %s", name)
    
    # 1. Create the campaign in DRAFT mode
    campaign = RevenueCampaign(
        name=name,
        created_by_agent="Visionary",
        status=CampaignStatus.DRAFT.value,
        budget_cents=budget_cents,
        target_revenue_cents=target_revenue_cents,
        actual_revenue_cents=0,
    )
    db.add(campaign)
    await db.flush()
    
    # 2. Create an approval request for the CEO
    approval = Approval(
        item_type="campaign",
        item_id=campaign.id,
        requested_by_agent="Visionary",
        status=ApprovalStatus.PENDING.value,
    )
    db.add(approval)
    await db.flush()
    
    return campaign
