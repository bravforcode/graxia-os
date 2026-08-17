"""
graxia/packages/revenue_os/agents/sales.py
Sales Agent — drafts outreach emails to leads and requests approval.

P1-9: persists token usage (prompt_tokens/completion_tokens) so LLM cost can
be tracked. Uses current model fields (output=, object_type/object_id).
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import ApprovalStatus
from ..models import AIDraft, Approval, Lead

logger = logging.getLogger(__name__)


async def draft_outreach_email(
    db: AsyncSession,
    lead: Lead,
    content: str,
    subject: str,
    prompt: Optional[str] = None,
    model_used: str = "claude-sonnet-4.6",
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
) -> AIDraft:
    """
    Sales agent logic: Draft an outreach email for a Lead.
    Automatically attaches an approval request.

    Draft is created FIRST, then approval references draft.id (not circular
    UUID fabrication). Token usage persisted for LLM cost tracking (P1-9).
    """
    logger.info("Sales Agent drafting email for lead: %s", lead.email)

    # 1. Create the AI draft FIRST (persist tokens for cost tracking)
    draft = AIDraft(
        draft_type="email_draft",
        generated_by_agent="Sales",
        lead_id=lead.id,
        prompt=prompt,
        output=content,
        subject=subject,
        model_used=model_used,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    db.add(draft)
    await db.flush()  # Flush to get draft.id

    # 2. Create an approval request that references the draft
    approval = Approval(
        object_type="ai_draft",
        object_id=draft.id,
        ai_draft_id=draft.id,
        requested_by_agent="Sales",
        status=ApprovalStatus.PENDING,
    )
    db.add(approval)
    await db.flush()

    # 3. Link back (approval_id on the draft)
    draft.approval_id = approval.id
    await db.flush()

    return draft