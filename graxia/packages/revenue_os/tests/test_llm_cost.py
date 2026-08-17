"""Tests for sales agent draft + LLM cost tracking (P1-9)."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.sales import draft_outreach_email
from ..models import AIDraft, Approval, Lead
from ..services.llm_cost import llm_cost_summary


@pytest.mark.asyncio
async def test_draft_outreach_email_persists_tokens(db_session: AsyncSession):
    lead = Lead(email="lead@example.com", name="Lead", source="facebook", score=50)
    db_session.add(lead)
    await db_session.flush()

    draft = await draft_outreach_email(
        db_session, lead, content="Hello!", subject="Hi",
        prompt="Write email", model_used="claude-sonnet-4.6",
        prompt_tokens=100, completion_tokens=50,
    )
    assert draft.output == "Hello!"
    assert draft.prompt_tokens == 100
    assert draft.completion_tokens == 50
    assert draft.model_used == "claude-sonnet-4.6"

    # Approval references the draft with current model fields
    approval = await db_session.scalar(
        select(Approval).where(Approval.ai_draft_id == draft.id)
    )
    assert approval is not None
    assert approval.object_type == "ai_draft"
    assert approval.object_id == draft.id
    assert draft.approval_id == approval.id


@pytest.mark.asyncio
async def test_llm_cost_summary(db_session: AsyncSession):
    lead = Lead(email="lead2@example.com", name="Lead2", source="facebook", score=50)
    db_session.add(lead)
    await db_session.flush()

    await draft_outreach_email(
        db_session, lead, content="A", subject="S", model_used="claude-sonnet-4.6",
        prompt_tokens=1000, completion_tokens=1000,
    )
    await draft_outreach_email(
        db_session, lead, content="B", subject="T", model_used="claude-3-haiku-20240307",
        prompt_tokens=1000, completion_tokens=1000,
    )

    summary = await llm_cost_summary(db_session)
    assert summary["total_tokens"] == 4000
    # sonnet: 2000/1000*0.30 = 0.60 ; haiku: 2000/1000*0.05 = 0.10
    assert summary["estimated_cost_thb"] == pytest.approx(0.70, abs=0.001)
    assert len(summary["by_model"]) == 2