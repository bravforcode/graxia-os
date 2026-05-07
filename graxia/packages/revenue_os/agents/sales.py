"""
graxia/packages/revenue_os/agents/sales.py
Sales Agent — responsible for drafting emails to leads and requesting approval.
"""
from __future__ import annotations

import logging
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import Lead, AIDraft, Approval, ApprovalStatus

logger = logging.getLogger(__name__)

async def draft_outreach_email(db: AsyncSession, lead: Lead, content: str, subject: str) -> AIDraft:
    """
    Sales agent logic: Draft an outreach email for a Lead.
    Automatically attaches an approval request.
    
    FIXED: Draft is created FIRST, then approval references draft.id (not circular UUID fabrication).
    """
    logger.info("Sales Agent drafting email for lead: %s", lead.email)
    
    # 1. Create the AI draft FIRST
    draft = AIDraft(
        draft_type="email_draft",
        generated_by_agent="Sales",
        lead_id=lead.id,
        campaign_id=lead.campaign_id,
        content=content,
        subject=subject,
        model_used="claude-3-haiku-20240307",
    )
    db.add(draft)
    await db.flush()  # Flush to get draft.id
    
    # 2. Create an approval request that references the draft
    approval = Approval(
        item_type="ai_draft",
        item_id=draft.id,
        requested_by_agent="Sales",
        status=ApprovalStatus.PENDING.value,
    )
    db.add(approval)
    await db.flush()
    
    # 3. Link the approval back to the draft
    draft.approval_id = approval.id
    
    return draft
