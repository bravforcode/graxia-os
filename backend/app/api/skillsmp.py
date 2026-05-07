"""SkillsMP API Endpoints - AI Learning & Skill Management"""

import logging
import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.skill_learning_engine import SkillLearningEngine
from app.core.skill_recommender import SkillRecommender
from app.database import get_db
from app.jobs.skillsmp_sync import run_hourly_sync
from app.models.skillsmp_skill import SkillInvocation, SkillLearningLog, SkillsMPSkill
from app.schemas.skillsmp import (
    LearningLogOut,
    SkillAnalysisRequest,
    SkillAnalysisResponse,
    SkillContentResponse,
    SkillDiscoverResponse,
    SkillFeedbackRequest,
    SkillFeedbackResponse,
    SkillImprovementResponse,
    SkillInvokeRequest,
    SkillInvokeResponse,
    SkillRecommendationOut,
    SkillRecommendationRequest,
    SkillRecommendationResponse,
    SkillSearchRequest,
    SkillSearchResponse,
    SkillsMPSkillDetailOut,
    SkillsMPSkillList,
    SkillsMPSkillOut,
    SkillTypesResponse,
    SyncStatusResponse,
    SyncTriggerResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/skillsmp", tags=["SkillsMP AI Skills"])


# ============== Helper Functions ==============


async def get_skill_or_404(db: AsyncSession, skill_id: UUID) -> SkillsMPSkill:
    """Get skill or raise 404."""
    result = await db.execute(select(SkillsMPSkill).where(SkillsMPSkill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return skill


def get_openai_client() -> AsyncOpenAI:
    """Get OpenAI client."""
    client_kwargs = {"api_key": settings.OPENAI_API_KEY}
    if settings.OPENAI_BASE_URL:
        client_kwargs["base_url"] = settings.OPENAI_BASE_URL
    return AsyncOpenAI(**client_kwargs)


# ============== List & Detail Endpoints ==============


@router.get("/skills", response_model=SkillsMPSkillList)
async def list_skills(
    db: AsyncSession = Depends(get_db),
    skill_type: str | None = Query(None, description="Filter by skill type"),
    tag: str | None = Query(None, description="Filter by context tag"),
    min_effectiveness: float = Query(0, ge=0, le=100),
    active_only: bool = Query(True, description="Exclude deleted-at-source skills"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> SkillsMPSkillList:
    """List all SkillsMP skills with filtering."""
    query = select(SkillsMPSkill)

    if skill_type:
        query = query.where(SkillsMPSkill.source_type == skill_type)

    if active_only:
        query = query.where(not SkillsMPSkill.is_deleted_at_source)

    if min_effectiveness > 0:
        query = query.where(SkillsMPSkill.effectiveness_score >= min_effectiveness)

    # Tag filter (JSONB contains)
    if tag:
        query = query.where(SkillsMPSkill.context_tags.contains([tag]))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = (
        query.order_by(
            desc(SkillsMPSkill.effectiveness_score),
            desc(SkillsMPSkill.usage_count),
            SkillsMPSkill.name,
        )
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(query)
    skills = result.scalars().all()

    return SkillsMPSkillList(
        total=total or 0,
        items=[SkillsMPSkillOut.from_orm(s) for s in skills],
        page=(offset // limit) + 1,
        limit=limit,
    )


@router.get("/skills/{skill_id}", response_model=SkillsMPSkillDetailOut)
async def get_skill(
    skill_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SkillsMPSkillDetailOut:
    """Get detailed skill information."""
    skill = await get_skill_or_404(db, skill_id)

    # Build response with all fields
    data = {
        "id": skill.id,
        "external_id": skill.external_id,
        "source_type": skill.source_type,
        "name": skill.name,
        "description": skill.description,
        "content_preview": (skill.content or "")[:500] + "..."
        if skill.content and len(skill.content) > 500
        else skill.content,
        "skill_metadata": skill.skill_metadata or {},
        "usage_count": skill.usage_count or 0,
        "success_rate": skill.success_rate or 0,
        "effectiveness_score": skill.effectiveness_score or 0,
        "last_used_at": skill.last_used_at,
        "context_tags": skill.context_tags or [],
        "trigger_patterns": skill.trigger_patterns or [],
        "related_skill_ids": skill.related_skill_ids or [],
        "version": skill.version or 1,
        "has_ai_improvement": bool(skill.ai_improved_version),
        "created_at": skill.created_at,
        "updated_at": skill.updated_at,
        "last_synced_at": skill.last_synced_at,
        "content": skill.content,
        "ai_improved_content": skill.ai_improved_version,
        "previous_versions": skill.previous_versions or [],
    }

    return SkillsMPSkillDetailOut(**data)


@router.get("/skills/{skill_id}/content", response_model=SkillContentResponse)
async def get_skill_content(
    skill_id: UUID,
    prefer_improved: bool = Query(True, description="Use AI-improved version if available"),
    include_history: bool = Query(False, description="Include version history"),
    db: AsyncSession = Depends(get_db),
) -> SkillContentResponse:
    """Get skill content for direct injection into system prompts."""
    skill = await get_skill_or_404(db, skill_id)

    # Determine which content to return
    content = (
        skill.ai_improved_version
        if (prefer_improved and skill.ai_improved_version)
        else skill.content
    )
    is_improved = bool(prefer_improved and skill.ai_improved_version)

    return SkillContentResponse(
        id=skill.id,
        name=skill.name,
        skill_type=skill.source_type,
        content=content or "",
        is_improved_version=is_improved,
        version=skill.version or 1,
        metadata=skill.metadata or {},
        effectiveness_score=skill.effectiveness_score or 0,
        previous_versions=skill.previous_versions if include_history else None,
    )


@router.get("/skills/{skill_id}/logs", response_model=list[LearningLogOut])
async def get_skill_logs(
    skill_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[LearningLogOut]:
    """Get learning logs for a skill."""
    # Verify skill exists
    await get_skill_or_404(db, skill_id)

    result = await db.execute(
        select(SkillLearningLog)
        .where(SkillLearningLog.skill_id == skill_id)
        .order_by(desc(SkillLearningLog.created_at))
        .limit(limit)
    )
    logs = result.scalars().all()

    return [LearningLogOut.model_validate(log) for log in logs]


# ============== Invocation Endpoints (A + B + C) ==============


@router.post("/invoke", response_model=SkillInvokeResponse)
async def invoke_skill(
    request: SkillInvokeRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> SkillInvokeResponse:
    """
    A) Direct skill invocation with AI processing.

    Uses skill content as enhanced system prompt to complete the task.
    """
    start_time = time.time()

    skill = await get_skill_or_404(db, request.skill_id)

    # Get content (prefer improved version if requested)
    skill_content = (
        skill.ai_improved_version
        if (request.prefer_improved and skill.ai_improved_version)
        else skill.content
    )

    if not skill_content:
        raise HTTPException(status_code=400, detail=f"Skill {skill.id} has no content")

    # Build enhanced prompt
    enhanced_system = f"""You are an expert assistant. Use the following skill methodology to complete the task:

=== SKILL: {skill.name} ===
{skill_content}

=== TASK ===
Apply the above skill methodology to complete the user's task. Be thorough and follow the instructions precisely."""

    # Call AI
    client = get_openai_client()
    model = request.model or settings.DEFAULT_LLM_MODEL

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": enhanced_system},
                {"role": "user", "content": request.task},
            ],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        execution_time = int((time.time() - start_time) * 1000)

        # Record invocation
        invocation = SkillInvocation(
            skill_id=skill.id,
            invocation_type="direct",
            task_context=request.task[:500],
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            success=True,  # Will be updated by feedback
            execution_time_ms=execution_time,
        )
        db.add(invocation)

        # Record usage for learning (async background)
        engine = SkillLearningEngine(db, client)
        background.add_task(
            engine.record_usage,
            skill_id=skill.id,
            context=request.task[:200],
            success=True,
            outcome_quality=0.8,
            invocation_type="direct",
            execution_time_ms=execution_time,
        )

        await db.commit()

        return SkillInvokeResponse(
            skill_id=skill.id,
            skill_name=skill.name,
            skill_type=skill.source_type,
            response=response.choices[0].message.content,
            model_used=model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
            skill_effectiveness=skill.effectiveness_score or 0,
            execution_time_ms=execution_time,
        )

    except Exception as e:
        logger.error(f"Skill invocation failed: {e}")

        # Record failed invocation
        invocation = SkillInvocation(
            skill_id=skill.id,
            invocation_type="direct",
            task_context=request.task[:500],
            success=False,
            execution_time_ms=int((time.time() - start_time) * 1000),
        )
        db.add(invocation)
        await db.commit()

        raise HTTPException(status_code=500, detail=f"Skill invocation failed: {str(e)}")


@router.post("/skills/{skill_id}/feedback", response_model=SkillFeedbackResponse)
async def submit_skill_feedback(
    skill_id: UUID,
    request: SkillFeedbackRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> SkillFeedbackResponse:
    """Submit feedback to improve skill effectiveness scoring."""
    skill = await get_skill_or_404(db, skill_id)

    # Record feedback
    engine = SkillLearningEngine(db, get_openai_client())
    await engine.submit_feedback(
        skill_id=skill.id,
        rating=request.rating,
        feedback_text=request.feedback_text,
        context=request.context,
    )

    # Check if improvement was triggered
    improvement_triggered = (
        request.rating <= 2 and skill.usage_count >= 5 and not skill.ai_improved_version
    )

    # Refresh skill data
    await db.refresh(skill)

    return SkillFeedbackResponse(
        skill_id=skill.id,
        new_effectiveness=skill.effectiveness_score or 0,
        new_success_rate=skill.success_rate or 0,
        improvement_triggered=improvement_triggered,
        message="Feedback recorded. Thank you for helping improve the skill!"
        if request.rating >= 4
        else "Feedback recorded. We'll work on improving this skill.",
    )


# ============== Search Endpoint (C - RAG) ==============


@router.post("/search", response_model=SkillSearchResponse)
async def search_skills(
    request: SkillSearchRequest,
    db: AsyncSession = Depends(get_db),
) -> SkillSearchResponse:
    """
    C) RAG-based semantic search with recommendation engine.
    """
    recommender = SkillRecommender(db)

    # Search using recommender
    results = await recommender.search(
        query=request.query,
        skill_type=request.skill_type,
        min_effectiveness=request.min_effectiveness,
        limit=request.limit,
    )

    # Try to find a skill chain if context provided
    suggested_chain = None
    if request.context:
        chain = await recommender.find_skill_chain(
            task_description=f"{request.query} {request.context}",
        )
        if chain:
            suggested_chain = chain  # Will be serialized by Pydantic

    return SkillSearchResponse(
        query=request.query,
        context=request.context,
        results=results,
        total_found=len(results),
        suggested_chain=suggested_chain,
    )


# ============== Recommendation Endpoints ==============


@router.post("/recommend", response_model=SkillRecommendationResponse)
async def recommend_skills(
    request: SkillRecommendationRequest,
    db: AsyncSession = Depends(get_db),
) -> SkillRecommendationResponse:
    """Get skill recommendations based on task context."""
    recommender = SkillRecommender(db)

    recommendations = await recommender.recommend(
        task_context=request.task_context,
        current_skill_ids=request.current_skill_ids,
        preferred_types=request.preferred_types,
        limit=request.limit,
    )

    return SkillRecommendationResponse(
        recommendations=recommendations,
        query=request.task_context[:100],
        total_found=len(recommendations),
    )


@router.get("/discover", response_model=SkillDiscoverResponse)
async def discover_skills(
    current_context: str,
    db: AsyncSession = Depends(get_db),
) -> SkillDiscoverResponse:
    """Discover skills based on current work context."""
    recommender = SkillRecommender(db)

    # Get recommendations
    recommendations = await recommender.recommend(
        task_context=current_context,
        limit=5,
    )

    # Identify gaps
    gaps = await recommender.get_skill_gaps(current_context)

    # Build suggested learning
    suggested_learning = [
        {
            "reason": gap["reason"],
            "suggested_skill_type": gap["type"],
            "example_query": f"How can I use {gap['type']} skills for this task?",
        }
        for gap in gaps
    ]

    return SkillDiscoverResponse(
        recommended_skills=recommendations,
        skill_gaps=gaps,
        suggested_learning=suggested_learning,
    )


@router.get("/discover-by-trigger", response_model=list[SkillRecommendationOut])
async def discover_by_trigger(
    context_text: str,
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> list[SkillRecommendationOut]:
    """Discover skills by trigger pattern matching."""
    recommender = SkillRecommender(db)
    return await recommender.discover_by_trigger(context_text, limit)


# ============== Sync Endpoints ==============


@router.post("/sync/trigger", response_model=SyncTriggerResponse)
async def trigger_sync(
    background: BackgroundTasks,
    full_sync: bool = True,
    db: AsyncSession = Depends(get_db),
) -> SyncTriggerResponse:
    """Manually trigger hourly sync."""
    # Check if API key is configured
    from app.config import settings

    # Note: SKILLSMP_API_KEY should be added to settings
    api_key = getattr(settings, "SKILLSMP_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="SKILLSMP_API_KEY not configured")

    # Run sync in background
    background.add_task(run_hourly_sync, db, api_key)

    return SyncTriggerResponse(
        status="started",
        job_id=f"sync_{int(time.time())}",
        message="Sync job started in background",
        estimated_duration_seconds=300,  # ~5 minutes
    )


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status(
    db: AsyncSession = Depends(get_db),
) -> SyncStatusResponse:
    """Get last sync status and stats."""
    # Get last synced skill
    result = await db.execute(
        select(SkillsMPSkill.last_synced_at)
        .where(not SkillsMPSkill.is_deleted_at_source)
        .order_by(desc(SkillsMPSkill.last_synced_at))
        .limit(1)
    )
    last_sync = result.scalar_one_or_none()

    # Get total counts
    total_result = await db.execute(
        select(func.count())
        .select_from(SkillsMPSkill)
        .where(not SkillsMPSkill.is_deleted_at_source)
    )
    total_skills = total_result.scalar() or 0

    # Get counts by type
    type_result = await db.execute(
        select(SkillsMPSkill.source_type, func.count())
        .where(not SkillsMPSkill.is_deleted_at_source)
        .group_by(SkillsMPSkill.source_type)
    )
    by_type = {row[0]: {"count": row[1]} for row in type_result.all()}

    # Get AI improved count
    improved_result = await db.execute(
        select(func.count())
        .select_from(SkillsMPSkill)
        .where(SkillsMPSkill.ai_improved_version is not None)
        .where(not SkillsMPSkill.is_deleted_at_source)
    )
    ai_improved = improved_result.scalar() or 0

    # Get high effectiveness count (>= 70)
    high_eff_result = await db.execute(
        select(func.count())
        .select_from(SkillsMPSkill)
        .where(SkillsMPSkill.effectiveness_score >= 70)
        .where(not SkillsMPSkill.is_deleted_at_source)
    )
    high_effectiveness = high_eff_result.scalar() or 0

    # Calculate next scheduled (hourly)
    next_scheduled = None
    if last_sync:
        from datetime import timedelta

        next_scheduled = last_sync + timedelta(hours=1)

    return SyncStatusResponse(
        last_sync=last_sync,
        next_scheduled=next_scheduled,
        is_running=False,  # Would need job tracking to know this
        total_skills=total_skills,
        by_type=by_type,
        ai_improved=ai_improved,
        high_effectiveness=high_effectiveness,
    )


# ============== Learning & Analysis Endpoints ==============


@router.post("/analyze", response_model=SkillAnalysisResponse)
async def analyze_skills(
    request: SkillAnalysisRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> SkillAnalysisResponse:
    """Analyze skill effectiveness and suggest improvements."""
    engine = SkillLearningEngine(db, get_openai_client())

    analysis = await engine.analyze_skill_effectiveness(
        skill_type=request.skill_type,
        min_usage=request.min_usage,
    )

    return SkillAnalysisResponse(**analysis)


@router.post("/skills/{skill_id}/improve", response_model=SkillImprovementResponse)
async def improve_skill(
    skill_id: UUID,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> SkillImprovementResponse:
    """Generate AI improvement for a skill."""
    skill = await get_skill_or_404(db, skill_id)

    engine = SkillLearningEngine(db, get_openai_client())
    improvement = await engine.generate_improvement(skill.id)

    if not improvement:
        # Not eligible
        return SkillImprovementResponse(
            skill_id=skill.id,
            skill_name=skill.name,
            improvement_generated=False,
            improvement_reason="Not eligible (insufficient usage or already improved)",
            new_version=skill.version,
        )

    return SkillImprovementResponse(
        skill_id=skill.id,
        skill_name=skill.name,
        improvement_generated=True,
        improvement_reason=improvement.improvement_reason,
        changes_summary=improvement.changes_summary,
        new_version=skill.version + 1,
        confidence_score=improvement.confidence_score,
    )


# ============== Type & Category Endpoints ==============


@router.get("/types", response_model=SkillTypesResponse)
async def get_skill_types(
    db: AsyncSession = Depends(get_db),
) -> SkillTypesResponse:
    """Get all available skill types with counts."""
    result = await db.execute(
        select(SkillsMPSkill.source_type, func.count())
        .where(not SkillsMPSkill.is_deleted_at_source)
        .group_by(SkillsMPSkill.source_type)
    )

    counts = {row[0]: row[1] for row in result.all()}
    types = list(counts.keys())

    # Ensure all default types are present
    default_types = ["openclaw", "claude", "codex", "hermes", "tool", "dev", "context"]
    for t in default_types:
        if t not in types:
            types.append(t)
            counts[t] = 0

    return SkillTypesResponse(
        types=types,
        counts=counts,
    )


@router.get("/tags", response_model=dict[str, int])
async def get_all_tags(
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Get all context tags with counts."""
    result = await db.execute(
        select(SkillsMPSkill.context_tags)
        .where(SkillsMPSkill.context_tags is not None)
        .where(not SkillsMPSkill.is_deleted_at_source)
    )

    tag_counts: dict[str, int] = {}
    for row in result.all():
        tags = row[0] or []
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    return dict(sorted(tag_counts.items(), key=lambda x: -x[1]))


# ============== Stats Endpoint ==============


@router.get("/stats", response_model=dict[str, Any])
async def get_stats(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get comprehensive SkillsMP statistics."""
    # Total skills
    total_result = await db.execute(select(func.count()).select_from(SkillsMPSkill))
    total = total_result.scalar() or 0

    # Active skills
    active_result = await db.execute(
        select(func.count())
        .select_from(SkillsMPSkill)
        .where(not SkillsMPSkill.is_deleted_at_source)
    )
    active = active_result.scalar() or 0

    # Total invocations
    invocations_result = await db.execute(select(func.count()).select_from(SkillInvocation))
    invocations = invocations_result.scalar() or 0

    # Average effectiveness
    eff_result = await db.execute(
        select(func.avg(SkillsMPSkill.effectiveness_score)).where(
            not SkillsMPSkill.is_deleted_at_source
        )
    )
    avg_effectiveness = float(eff_result.scalar() or 0)

    # Most used skills
    top_result = await db.execute(
        select(SkillsMPSkill)
        .where(not SkillsMPSkill.is_deleted_at_source)
        .order_by(desc(SkillsMPSkill.usage_count))
        .limit(5)
    )
    top_skills = top_result.scalars().all()

    return {
        "total_skills": total,
        "active_skills": active,
        "deleted_at_source": total - active,
        "total_invocations": invocations,
        "average_effectiveness": round(avg_effectiveness, 2),
        "top_skills": [
            {
                "id": str(s.id),
                "name": s.name,
                "usage_count": s.usage_count,
                "effectiveness": float(s.effectiveness_score or 0),
            }
            for s in top_skills
        ],
    }


# ============== Agent Learning Endpoints ==============

from app.core.agent_skill_bridge import get_agent_skill_bridge


class AgentSkillQueryRequest(BaseModel):
    """Request for agent to query skills."""

    agent_id: str
    task_description: str
    task_type: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class AgentLearnRequest(BaseModel):
    """Request for agent to record learning from a skill."""

    agent_id: str
    skill_id: UUID
    task_context: str
    success: bool = True
    quality: float = Field(default=0.8, ge=0, le=1)
    learnings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class AgentSkillProfileResponse(BaseModel):
    """Agent's skill learning profile."""

    agent_id: str
    top_skills: list[dict[str, Any]]
    total_skills_learned: int
    recommended_new_skills: list[dict[str, Any]]


class AgentLearningCycleRequest(BaseModel):
    """Request for continuous learning cycle."""

    agent_id: str
    recent_tasks: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/agent/query", response_model=list[dict[str, Any]])
async def agent_query_skills(
    request: AgentSkillQueryRequest,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Agent queries skills for a specific task.

    This endpoint allows any agent in the system to discover
    skills relevant to their current task.
    """
    bridge = await get_agent_skill_bridge(db)
    return await bridge.get_skills_for_task(
        agent_id=request.agent_id,
        task_description=request.task_description,
        task_type=request.task_type,
        limit=request.limit,
    )


@router.post("/agent/learn", response_model=dict[str, Any])
async def agent_learn_from_skill(
    request: AgentLearnRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Record agent learning from applying a skill.

    Agents call this after using a skill to:
    - Record effectiveness
    - Share learnings
    - Suggest improvements
    """
    bridge = await get_agent_skill_bridge(db)

    result = await bridge.learn_from_skill(
        agent_id=request.agent_id,
        skill_id=request.skill_id,
        task_context=request.task_context,
        application_result={
            "success": request.success,
            "quality": request.quality,
            "learnings": request.learnings,
            "suggestions": request.suggestions,
        },
    )

    return {
        "skill_id": str(result.skill_id),
        "skill_name": result.skill_name,
        "applied": result.applied,
        "effectiveness_score": float(result.effectiveness_score),
        "learnings_recorded": len(result.learnings),
    }


@router.get("/agent/profile/{agent_id}", response_model=AgentSkillProfileResponse)
async def get_agent_skill_profile(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
) -> AgentSkillProfileResponse:
    """
    Get skill learning profile for an agent.

    Shows what skills the agent has learned and
    recommends new skills to learn.
    """
    bridge = await get_agent_skill_bridge(db)
    profile = await bridge.get_agent_skill_profile(agent_id)
    return AgentSkillProfileResponse(**profile)


@router.post("/agent/learn-cycle", response_model=dict[str, Any])
async def agent_continuous_learning(
    request: AgentLearningCycleRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Run continuous learning cycle for an agent.

    Analyzes recent tasks and identifies:
    - Skills that should be learned
    - Patterns in successful tasks
    - Skill gaps to address
    """
    bridge = await get_agent_skill_bridge(db)
    return await bridge.continuous_learning_cycle(
        agent_id=request.agent_id,
        recent_tasks=request.recent_tasks,
    )
