"""
AI Generation Service — Feature 16
Service for AI-powered skill generation with quality assurance
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Integer, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.models.skill_ai_generation import (
    AIGenerationFeedback,
    AIGenerationRequest,
    AIGenerationTemplate,
)
from app.models.skillsmp_skill import SkillsMPSkill

logger = get_logger(__name__)


class AIGenerationService:
    """
    Service for AI-powered skill generation.

    Feature 16: AI Generation Service
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def submit_generation_request(
        self,
        natural_language_prompt: str | None = None,
        source_code: str | None = None,
        example_inputs: list[str] | None = None,
        example_outputs: list[str] | None = None,
        reference_skill_ids: list[UUID] | None = None,
        skill_type: str = "function",
        complexity_level: str = "medium",
        target_framework: str | None = None,
        requested_by_agent_id: UUID | None = None,
    ) -> AIGenerationRequest:
        """Submit a new AI generation request."""

        # Generate unique request key
        request_key = f"gen_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{str(uuid4())[:8]}"

        request = AIGenerationRequest(
            id=uuid4(),
            request_key=request_key,
            natural_language_prompt=natural_language_prompt,
            source_code=source_code,
            example_inputs=example_inputs or [],
            example_outputs=example_outputs or [],
            reference_skill_ids=reference_skill_ids or [],
            skill_type=skill_type,
            complexity_level=complexity_level,
            target_framework=target_framework,
            requested_by_agent_id=requested_by_agent_id,
            status="pending",
        )

        self.session.add(request)
        await self.session.commit()

        logger.info(f"AI generation request submitted: {request_key}")
        return request

    async def process_generation_request(
        self,
        request_id: UUID,
        generated_skill_data: dict[str, Any],
        quality_score: int,
        validation_passed: bool,
    ) -> AIGenerationRequest:
        """Process and store results of AI generation."""

        request = await self.session.get(AIGenerationRequest, request_id)
        if not request:
            raise ValueError(f"Generation request not found: {request_id}")

        # Create the generated skill
        skill = SkillsMPSkill(
            id=uuid4(),
            name=generated_skill_data["name"],
            description=generated_skill_data.get("description", ""),
            content=generated_skill_data["content"],
            skill_type=request.skill_type,
            complexity_level=request.complexity_level,
            created_by_agent_id=request.requested_by_agent_id,
        )

        self.session.add(skill)
        await self.session.flush()

        # Update request with results
        request.status = "completed" if validation_passed else "reviewing"
        request.generated_skill_id = skill.id
        request.quality_score = quality_score
        request.validation_passed = validation_passed
        request.completed_at = datetime.utcnow()

        await self.session.commit()

        logger.info(f"AI generation request completed: {request.request_key}")
        return request

    async def get_generation_template(
        self,
        template_key: str,
    ) -> AIGenerationTemplate | None:
        """Get a generation template by key."""
        result = await self.session.execute(
            select(AIGenerationTemplate).where(
                AIGenerationTemplate.template_key == template_key,
                AIGenerationTemplate.is_active,
            )
        )
        return result.scalar_one_or_none()

    async def list_generation_templates(
        self,
        skill_type: str | None = None,
        framework: str | None = None,
    ) -> list[AIGenerationTemplate]:
        """List available generation templates."""
        query = select(AIGenerationTemplate).where(AIGenerationTemplate.is_active)

        if skill_type:
            query = query.where(AIGenerationTemplate.skill_type == skill_type)
        if framework:
            query = query.where(AIGenerationTemplate.framework == framework)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def submit_feedback(
        self,
        request_id: UUID,
        generated_skill_id: UUID,
        rating: int,
        feedback_text: str | None = None,
        issues: list[str] | None = None,
        suggested_changes: list[dict] | None = None,
        provided_by_agent_id: UUID | None = None,
    ) -> AIGenerationFeedback:
        """Submit feedback on AI-generated skill."""

        feedback = AIGenerationFeedback(
            id=uuid4(),
            request_id=request_id,
            generated_skill_id=generated_skill_id,
            rating=rating,
            feedback_text=feedback_text,
            issues=issues or [],
            suggested_changes=suggested_changes or [],
            provided_by_agent_id=provided_by_agent_id,
        )

        self.session.add(feedback)
        await self.session.commit()

        logger.info(f"Feedback submitted for generation request: {request_id}")
        return feedback

    async def get_generation_statistics(
        self,
        agent_id: UUID | None = None,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get AI generation statistics."""
        from sqlalchemy import func

        query = select(
            func.count(AIGenerationRequest.id).label("total"),
            func.sum((AIGenerationRequest.status == "completed").cast(Integer)).label("completed"),
            func.avg(AIGenerationRequest.quality_score).label("avg_quality"),
        ).where(
            AIGenerationRequest.submitted_at
            >= datetime.utcnow().replace(day=datetime.utcnow().day - days)
        )

        if agent_id:
            query = query.where(AIGenerationRequest.requested_by_agent_id == agent_id)

        result = await self.session.execute(query)
        stats = result.one()

        return {
            "total_requests": stats.total or 0,
            "completed": stats.completed or 0,
            "success_rate": (stats.completed / stats.total * 100) if stats.total else 0,
            "average_quality_score": float(stats.avg_quality) if stats.avg_quality else 0,
        }
