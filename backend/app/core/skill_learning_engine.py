"""AI Skill Learning Engine - Self-Improvement & Skill Creation"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from openai import AsyncOpenAI
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.skillsmp_skill import SkillLearningLog, SkillsMPSkill

logger = logging.getLogger(__name__)


@dataclass
class LearningContext:
    """Context for AI learning operations."""

    task_description: str
    expected_outcome: str
    actual_outcome: str | None = None
    success_indicators: list[str] | None = None
    related_skills: list[UUID] | None = None


@dataclass
class SkillImprovement:
    """Result of skill improvement generation."""

    skill_id: UUID
    original_content: str
    improved_content: str
    improvement_reason: str
    confidence_score: Decimal
    changes_summary: list[str]


@dataclass
class NewSkillCandidate:
    """Candidate for new skill creation."""

    name: str
    description: str
    content: str
    skill_type: str
    context_tags: list[str]
    trigger_patterns: list[str]
    related_skill_ids: list[UUID]
    confidence_score: Decimal
    source_context: str


class SkillLearningEngine:
    """
    AI-powered skill evolution system.

    Capabilities:
    - Self-improves skills based on usage patterns
    - Creates new skills from successful work patterns
    - Learns from context and outcomes
    - Builds skill relationships and chains
    """

    # Thresholds for auto-improvement
    MIN_USAGE_FOR_IMPROVEMENT = 5
    MIN_USAGE_FOR_CREATION = 3
    SUCCESS_RATE_THRESHOLD = Decimal("70.00")
    EFFECTIVENESS_THRESHOLD = Decimal("50.00")

    def __init__(self, db: AsyncSession, openai_client: AsyncOpenAI | None = None):
        self.db = db
        if openai_client:
            self.openai = openai_client
        else:
            client_kwargs = {"api_key": settings.OPENAI_API_KEY}
            if settings.OPENAI_BASE_URL:
                client_kwargs["base_url"] = settings.OPENAI_BASE_URL
            self.openai = AsyncOpenAI(**client_kwargs)

    async def record_usage(
        self,
        skill_id: UUID,
        context: str,
        success: bool,
        outcome_quality: float = 0.8,
        invocation_type: str = "direct",
        execution_time_ms: int | None = None,
    ) -> SkillsMPSkill:
        """
        Record skill usage and update statistics.

        Args:
            skill_id: The skill UUID
            context: Task context (truncated description)
            success: Whether the skill application was successful
            outcome_quality: Quality score 0-1
            invocation_type: How the skill was invoked
            execution_time_ms: Execution time in milliseconds

        Returns:
            Updated skill
        """
        skill = await self._get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")

        # Update skill stats
        skill.update_usage_stats(success, outcome_quality)

        # Log the usage
        self.db.add(
            SkillLearningLog(
                skill_id=skill.id,
                learning_type="usage",
                context=context[:500],
                after_state={
                    "usage_count": skill.usage_count,
                    "success_rate": float(skill.success_rate),
                    "effectiveness_score": float(skill.effectiveness_score),
                    "invocation_type": invocation_type,
                },
                confidence_score=Decimal(str(outcome_quality)),
            )
        )

        await self.db.commit()
        await self.db.refresh(skill)

        logger.info(
            f"Recorded usage for skill '{skill.name}': "
            f"success={success}, quality={outcome_quality:.2f}, "
            f"total_usage={skill.usage_count}"
        )

        return skill

    async def submit_feedback(
        self,
        skill_id: UUID,
        rating: int,  # 1-5
        feedback_text: str | None = None,
        context: str | None = None,
    ) -> SkillsMPSkill:
        """
        Submit user/AI feedback for a skill.

        Args:
            skill_id: The skill UUID
            rating: Rating from 1-5
            feedback_text: Optional detailed feedback
            context: Task context

        Returns:
            Updated skill
        """
        skill = await self._get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")

        # Convert rating to success/outcome quality
        success = rating >= 3
        outcome_quality = rating / 5.0

        # Update stats
        skill.update_usage_stats(success, outcome_quality)

        # Log feedback
        self.db.add(
            SkillLearningLog(
                skill_id=skill.id,
                learning_type="feedback",
                context=context or feedback_text,
                after_state={
                    "rating": rating,
                    "feedback": feedback_text,
                    "success_rate": float(skill.success_rate),
                },
                confidence_score=Decimal(str(outcome_quality)),
            )
        )

        # Trigger auto-improvement if poor performance
        if rating <= 2 and skill.usage_count >= self.MIN_USAGE_FOR_IMPROVEMENT:
            logger.info(f"Poor rating ({rating}) for skill '{skill.name}', triggering improvement")
            await self.generate_improvement(skill_id)

        await self.db.commit()
        await self.db.refresh(skill)

        return skill

    async def generate_improvement(self, skill_id: UUID) -> SkillImprovement | None:
        """
        AI generates improved version of skill based on usage data.

        Args:
            skill_id: The skill UUID

        Returns:
            SkillImprovement if generated, None if not eligible
        """
        skill = await self._get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")

        # Check eligibility
        if skill.usage_count < self.MIN_USAGE_FOR_IMPROVEMENT:
            logger.info(
                f"Skill '{skill.name}' not eligible: usage_count={skill.usage_count} < {self.MIN_USAGE_FOR_IMPROVEMENT}"
            )
            return None

        if skill.success_rate > 95:
            logger.info(
                f"Skill '{skill.name}' already excellent: success_rate={skill.success_rate}%"
            )
            return None

        if skill.ai_improved_version:
            logger.info(f"Skill '{skill.name}' already has AI improvement")
            return None

        # Get learning logs for context
        logs = await self._get_learning_logs(skill_id, limit=20)

        # Build improvement prompt
        prompt = self._build_improvement_prompt(skill, logs)

        try:
            response = await self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at improving AI skills. Analyze the skill and suggest specific improvements.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4000,
            )

            improved_content = response.choices[0].message.content

            # Parse improvements
            changes_summary = self._extract_changes_summary(skill.content or "", improved_content)

            # Store improvement
            skill.add_ai_improvement(improved_content)

            # Log the improvement
            self.db.add(
                SkillLearningLog(
                    skill_id=skill.id,
                    learning_type="improvement",
                    context="AI auto-improvement generated",
                    before_state={
                        "version": skill.version - 1,
                        "success_rate": float(skill.success_rate),
                        "content_preview": (skill.content or "")[:500],
                    },
                    after_state={
                        "version": skill.version,
                        "improved_preview": improved_content[:500],
                        "changes": changes_summary,
                    },
                    confidence_score=Decimal("0.85"),
                )
            )

            await self.db.commit()
            await self.db.refresh(skill)

            improvement = SkillImprovement(
                skill_id=skill_id,
                original_content=skill.content or "",
                improved_content=improved_content,
                improvement_reason=f"Low success rate: {skill.success_rate}%",
                confidence_score=Decimal("0.85"),
                changes_summary=changes_summary,
            )

            logger.info(
                f"Generated improvement for skill '{skill.name}' with {len(changes_summary)} changes"
            )

            return improvement

        except Exception as e:
            logger.error(f"Failed to generate improvement for skill {skill_id}: {e}")
            return None

    async def create_skill_from_pattern(
        self,
        context: LearningContext,
    ) -> SkillsMPSkill | None:
        """
        Create new skill from discovered successful pattern.

        Args:
            context: Learning context with task details

        Returns:
            New skill if created, None otherwise
        """
        # Check if we have enough signal to create a skill
        if (
            not context.success_indicators
            or len(context.success_indicators) < self.MIN_USAGE_FOR_CREATION
        ):
            logger.info("Not enough success indicators to create skill")
            return None

        # Generate skill content
        prompt = self._build_skill_creation_prompt(context)

        try:
            response = await self.openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at creating reusable AI skills. Create a comprehensive skill based on the successful approach.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=4000,
            )

            generated = response.choices[0].message.content

            # Parse generated skill
            candidate = self._parse_skill_candidate(generated, context)

            # Create the skill
            new_skill = SkillsMPSkill(
                external_id=f"ai-generated-{uuid4()}",
                source_type="dev",  # AI-generated skills as dev type
                name=candidate.name,
                description=candidate.description,
                content=candidate.content,
                context_tags=candidate.context_tags,
                trigger_patterns=candidate.trigger_patterns,
                related_skill_ids=candidate.related_skill_ids,
                metadata={
                    "generated_from": context.task_description,
                    "generation_confidence": float(candidate.confidence_score),
                    "success_indicators": context.success_indicators,
                },
                effectiveness_score=candidate.confidence_score * 50,  # Starting score
            )

            self.db.add(new_skill)
            await self.db.flush()

            # Log creation
            self.db.add(
                SkillLearningLog(
                    skill_id=new_skill.id,
                    learning_type="creation",
                    context=f"AI generated from pattern: {context.task_description[:200]}",
                    after_state={
                        "name": candidate.name,
                        "type": "dev",
                        "related_skills": [str(s) for s in candidate.related_skill_ids],
                    },
                    confidence_score=candidate.confidence_score,
                )
            )

            await self.db.commit()
            await self.db.refresh(new_skill)

            logger.info(f"Created new AI skill: '{new_skill.name}' (ID: {new_skill.id})")

            return new_skill

        except Exception as e:
            logger.error(f"Failed to create skill from pattern: {e}")
            return None

    async def analyze_skill_effectiveness(
        self,
        skill_type: str | None = None,
        min_usage: int = 5,
    ) -> dict[str, Any]:
        """
        Analyze effectiveness of skills and suggest improvements.

        Args:
            skill_type: Filter by skill type
            min_usage: Minimum usage count for analysis

        Returns:
            Analysis report
        """
        query = (
            select(SkillsMPSkill)
            .where(SkillsMPSkill.usage_count >= min_usage)
            .where(not SkillsMPSkill.is_deleted_at_source)
        )

        if skill_type:
            query = query.where(SkillsMPSkill.source_type == skill_type)

        result = await self.db.execute(query)
        skills = result.scalars().all()

        if not skills:
            return {"message": "No skills meet criteria for analysis"}

        # Categorize skills
        high_performers = [
            s for s in skills if s.effectiveness_score and s.effectiveness_score >= 70
        ]
        needs_improvement = [
            s for s in skills if s.effectiveness_score and s.effectiveness_score < 50
        ]
        candidates_for_ai_improvement = [
            s
            for s in skills
            if s.success_rate
            and s.success_rate < 70
            and s.usage_count >= self.MIN_USAGE_FOR_IMPROVEMENT
            and not s.ai_improved_version
        ]

        # Generate improvement for candidates
        improvements_generated = 0
        for skill in candidates_for_ai_improvement[:5]:  # Limit to 5 per run
            improvement = await self.generate_improvement(skill.id)
            if improvement:
                improvements_generated += 1

        return {
            "total_analyzed": len(skills),
            "high_performers": len(high_performers),
            "needs_improvement": len(needs_improvement),
            "candidates_for_ai_improvement": len(candidates_for_ai_improvement),
            "improvements_generated": improvements_generated,
            "by_type": self._group_by_type(skills),
            "recommendations": self._generate_recommendations(skills),
        }

    async def _get_skill(self, skill_id: UUID) -> SkillsMPSkill | None:
        """Get skill by ID."""
        result = await self.db.execute(select(SkillsMPSkill).where(SkillsMPSkill.id == skill_id))
        return result.scalar_one_or_none()

    async def _get_learning_logs(
        self,
        skill_id: UUID,
        limit: int = 20,
    ) -> list[SkillLearningLog]:
        """Get learning logs for a skill."""
        result = await self.db.execute(
            select(SkillLearningLog)
            .where(SkillLearningLog.skill_id == skill_id)
            .order_by(desc(SkillLearningLog.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    def _build_improvement_prompt(
        self,
        skill: SkillsMPSkill,
        logs: list[SkillLearningLog],
    ) -> str:
        """Build prompt for skill improvement."""
        recent_contexts = [log.context for log in logs if log.context][:5]

        return f"""Analyze this skill and suggest improvements based on usage data:

Skill Name: {skill.name}
Description: {skill.description or "N/A"}
Current Success Rate: {skill.success_rate}%
Usage Count: {skill.usage_count}
Effectiveness Score: {skill.effectiveness_score}

Recent Usage Contexts:
{chr(10).join(f"- {ctx[:200]}" for ctx in recent_contexts) if recent_contexts else "No recent context available"}

Current Content:
{skill.content or "No content"}

Please provide an improved version that:
1. Addresses the low success rate ({skill.success_rate}%)
2. Makes the instructions clearer and more specific
3. Adds examples where helpful
4. Improves error handling guidance
5. Maintains the same overall purpose

Return the complete improved markdown content with YAML frontmatter:

---
name: {skill.name}
description: [improved description]
version: {skill.version + 1}
---

[improved content]
"""

    def _build_skill_creation_prompt(self, context: LearningContext) -> str:
        """Build prompt for skill creation."""
        return f"""Create a reusable AI skill based on this successful approach:

Task Description:
{context.task_description}

Expected Outcome:
{context.expected_outcome}

Actual Outcome:
{context.actual_outcome or "Successful completion"}

Success Indicators Observed:
{chr(10).join(f"- {indicator}" for indicator in (context.success_indicators or []))}

Create a comprehensive skill with:
1. Clear name and description
2. Step-by-step instructions
3. When to use (trigger patterns)
4. Domain tags
5. Examples
6. Common pitfalls to avoid

Format as markdown with YAML frontmatter:

---
name: [skill name]
description: [when and how to use]
type: [openclaw/claude/codex/hermes/tool/dev/context]
tags: [relevant tags]
triggers: [patterns that activate this skill]
---

[detailed content]
"""

    def _extract_changes_summary(self, original: str, improved: str) -> list[str]:
        """Extract summary of changes between versions."""
        changes = []

        if len(improved) > len(original) * 1.2:
            changes.append("Added more detailed instructions")

        if "example" in improved.lower() and "example" not in original.lower():
            changes.append("Added examples")

        if "error" in improved.lower() and "error" not in original.lower():
            changes.append("Added error handling guidance")

        if not changes:
            changes.append("General improvements to clarity")

        return changes

    def _parse_skill_candidate(self, content: str, context: LearningContext) -> NewSkillCandidate:
        """Parse generated skill content."""
        # Extract frontmatter
        name = "Generated Skill"
        description = "AI-generated skill"
        skill_type = "dev"
        tags = []
        triggers = []

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                for line in frontmatter.strip().split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip()
                        value = value.strip().strip("\"'")

                        if key == "name":
                            name = value
                        elif key == "description":
                            description = value
                        elif key == "type":
                            skill_type = value
                        elif key == "tags":
                            tags = [t.strip() for t in value.strip("[]").split(",") if t.strip()]
                        elif key == "triggers":
                            triggers = [
                                t.strip() for t in value.strip("[]").split(",") if t.strip()
                            ]

                content = parts[2].strip()

        return NewSkillCandidate(
            name=name,
            description=description,
            content=content,
            skill_type=skill_type,
            context_tags=tags or context.success_indicators or ["ai-generated"],
            trigger_patterns=triggers or [context.task_description[:100]],
            related_skill_ids=context.related_skills or [],
            confidence_score=Decimal("0.80"),
            source_context=context.task_description,
        )

    def _group_by_type(self, skills: list[SkillsMPSkill]) -> dict[str, dict]:
        """Group skills by type with stats."""
        by_type: dict[str, list[SkillsMPSkill]] = {}

        for skill in skills:
            if skill.source_type not in by_type:
                by_type[skill.source_type] = []
            by_type[skill.source_type].append(skill)

        return {
            skill_type: {
                "count": len(type_skills),
                "avg_effectiveness": sum(float(s.effectiveness_score or 0) for s in type_skills)
                / len(type_skills)
                if type_skills
                else 0,
                "total_usage": sum(s.usage_count or 0 for s in type_skills),
            }
            for skill_type, type_skills in by_type.items()
        }

    def _generate_recommendations(self, skills: list[SkillsMPSkill]) -> list[str]:
        """Generate recommendations based on analysis."""
        recommendations = []

        low_performers = [s for s in skills if s.effectiveness_score and s.effectiveness_score < 30]
        if low_performers:
            recommendations.append(
                f"{len(low_performers)} skills have very low effectiveness. "
                f"Consider reviewing: {', '.join(s.name for s in low_performers[:3])}"
            )

        unused = [s for s in skills if s.usage_count == 0]
        if len(unused) > len(skills) * 0.5:
            recommendations.append(
                f"{len(unused)} skills have never been used. Consider promoting them or reviewing relevance."
            )

        return recommendations
