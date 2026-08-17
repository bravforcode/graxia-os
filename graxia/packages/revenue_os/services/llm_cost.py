"""LLM cost tracking (P1-9).

Sums persisted AIDraft token usage × per-model rate. Rates are approximate
(THB per 1K tokens, blended input+output) and configurable — replace with
real billing data before quoting to investors.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AIDraft

# THB per 1K tokens (blended input+output) — APPROXIMATE, configurable.
MODEL_RATES_THB_PER_1K: dict[str, float] = {
    "claude-sonnet-4.6": 0.30,
    "claude-3-haiku-20240307": 0.05,
    "claude-3-5-sonnet-20241022": 0.30,
}
DEFAULT_RATE_THB_PER_1K = 0.30


async def llm_cost_summary(db: AsyncSession) -> dict:
    """Aggregate token usage + estimated cost from AIDraft rows."""
    rows = (
        await db.execute(
            select(
                AIDraft.model_used,
                func.coalesce(func.sum(AIDraft.prompt_tokens), 0),
                func.coalesce(func.sum(AIDraft.completion_tokens), 0),
                func.count(AIDraft.id),
            ).group_by(AIDraft.model_used)
        )
    ).all()

    by_model = []
    total_tokens = 0
    total_cost = 0.0
    for model, prompt_tokens, completion_tokens, count in rows:
        tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)
        rate = MODEL_RATES_THB_PER_1K.get(model or "", DEFAULT_RATE_THB_PER_1K)
        cost = tokens / 1000 * rate
        total_tokens += tokens
        total_cost += cost
        by_model.append({
            "model": model or "unknown",
            "prompt_tokens": int(prompt_tokens or 0),
            "completion_tokens": int(completion_tokens or 0),
            "total_tokens": tokens,
            "drafts": int(count or 0),
            "estimated_cost_thb": round(cost, 4),
        })

    return {
        "total_tokens": total_tokens,
        "estimated_cost_thb": round(total_cost, 4),
        "by_model": by_model,
        "note": "rates approximate — replace with real billing data",
    }