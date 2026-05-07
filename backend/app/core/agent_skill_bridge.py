"""
Agent Skill Bridge - Continuous Learning Interface

Allows all agents in the system to:
1. Query and discover skills based on context
2. Learn from skill content continuously
3. Track what skills work best for specific tasks
4. Get personalized skill recommendations
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.skill_learning_engine import SkillLearningEngine
from app.core.skill_recommender import SkillRecommender
from app.models.skillsmp_skill import SkillLearningLog, SkillsMPSkill

logger = logging.getLogger(__name__)


@dataclass
class AgentSkillContext:
    """Context for agent skill learning."""

    agent_id: str
    task_type: str
    task_description: str
    current_skills: list[UUID] = field(default_factory=list)
    success_patterns: list[str] = field(default_factory=list)
    failure_patterns: list[str] = field(default_factory=list)


@dataclass
class SkillLearningResult:
    """Result of agent learning from a skill."""

    skill_id: UUID
    skill_name: str
    applied: bool
    effectiveness_score: Decimal
    learnings: list[str]
    suggested_improvements: list[str]


class AgentSkillBridge:
    """
    Bridge for agents to continuously learn from SkillsMP.

    This enables all agents in the system to:
    - Discover skills relevant to their current task
    - Learn from skill content and apply best practices
    - Contribute feedback to improve skills
    - Build personalized skill profiles
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.learning_engine = SkillLearningEngine(db)
        self.recommender = SkillRecommender(db)

    async def get_skills_for_task(
        self,
        agent_id: str,
        task_description: str,
        task_type: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Get recommended skills for a specific task.

        Args:
            agent_id: Unique agent identifier
            task_description: Description of the task
            task_type: Optional task category
            limit: Number of skills to return

        Returns:
            List of skill recommendations with relevance scores
        """
        # Use the recommender to find relevant skills (disable cache to avoid UUID serialization issues)
        recommendations = await self.recommender.recommend(
            task_context=task_description,
            preferred_types=[task_type] if task_type else [],
            limit=limit,
            use_cache=False,
        )

        # Format for agent consumption
        results = []
        for rec in recommendations:
            results.append(
                {
                    "skill_id": str(rec.skill_id),
                    "name": rec.name,
                    "description": rec.description,
                    "skill_type": rec.skill_type,
                    "content_preview": rec.content_preview,
                    "relevance_score": float(rec.score),
                    "effectiveness": float(rec.effectiveness),
                    "match_reasons": rec.match_reasons,
                }
            )

        logger.info(
            f"Agent {agent_id} queried {len(results)} skills for task: {task_description[:50]}..."
        )
        return results

    async def learn_from_skill(
        self,
        agent_id: str,
        skill_id: UUID,
        task_context: str,
        application_result: dict[str, Any],
    ) -> SkillLearningResult:
        """
        Record agent learning from a skill.

        Args:
            agent_id: Agent identifier
            skill_id: Skill that was used
            task_context: Context where skill was applied
            application_result: Result of applying the skill
                - success: bool
                - quality: float (0-1)
                - learnings: list[str]
                - suggestions: list[str]

        Returns:
            Learning result with effectiveness score
        """
        # Get skill details
        skill = await self.db.get(SkillsMPSkill, skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")

        # Record usage through learning engine
        success = application_result.get("success", False)
        quality = application_result.get("quality", 0.5)

        await self.learning_engine.record_usage(
            skill_id=skill_id,
            context=task_context,
            success=success,
            outcome_quality=quality,
            invocation_type="agent",
        )

        # Build learning result
        result = SkillLearningResult(
            skill_id=skill_id,
            skill_name=skill.name,
            applied=success,
            effectiveness_score=Decimal(str(quality * 100)),
            learnings=application_result.get("learnings", []),
            suggested_improvements=application_result.get("suggestions", []),
        )

        # If there are suggestions, log them for potential skill improvement
        if result.suggested_improvements:
            self.db.add(
                SkillLearningLog(
                    skill_id=skill_id,
                    learning_type="agent_feedback",
                    context=f"Agent {agent_id} feedback",
                    before_state={"agent_id": agent_id, "task": task_context[:200]},
                    after_state={"suggestions": result.suggested_improvements},
                    confidence_score=Decimal(str(quality)),
                )
            )
            await self.db.commit()

        logger.info(
            f"Agent {agent_id} learned from skill '{skill.name}': "
            f"applied={success}, quality={quality:.2f}"
        )

        return result

    async def get_agent_skill_profile(
        self,
        agent_id: str,
    ) -> dict[str, Any]:
        """
        Get skill learning profile for an agent.

        Shows:
        - Most used skills
        - Highest effectiveness skills
        - Learning progress over time
        - Recommended skills to learn
        """
        # Query skill usage by this agent
        result = await self.db.execute(
            select(
                SkillsMPSkill.id,
                SkillsMPSkill.name,
                SkillsMPSkill.source_type,
                func.count(SkillLearningLog.id).label("usage_count"),
                func.avg(SkillLearningLog.confidence_score).label("avg_quality"),
            )
            .join(SkillLearningLog, SkillsMPSkill.id == SkillLearningLog.skill_id)
            .where(
                SkillLearningLog.learning_type == "agent_feedback",
                SkillLearningLog.after_state.contains({"agent_id": agent_id}),
            )
            .group_by(SkillsMPSkill.id, SkillsMPSkill.name, SkillsMPSkill.source_type)
            .order_by(desc("usage_count"))
            .limit(10)
        )

        top_skills = []
        for row in result.fetchall():
            top_skills.append(
                {
                    "skill_id": str(row.id),
                    "name": row.name,
                    "type": row.source_type,
                    "usage_count": row.usage_count,
                    "avg_quality": float(row.avg_quality or 0),
                }
            )

        return {
            "agent_id": agent_id,
            "top_skills": top_skills,
            "total_skills_learned": len(top_skills),
            "recommended_new_skills": await self._get_new_skill_recommendations(agent_id),
        }

    async def _get_new_skill_recommendations(
        self,
        agent_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Get skills the agent hasn't learned yet but might benefit from."""
        # Find high-effectiveness skills not yet used by this agent
        result = await self.db.execute(
            select(SkillsMPSkill)
            .where(
                SkillsMPSkill.effectiveness_score >= 70,
                SkillsMPSkill.usage_count >= 5,
                ~SkillsMPSkill.id.in_(
                    select(SkillLearningLog.skill_id).where(
                        SkillLearningLog.after_state.contains({"agent_id": agent_id}),
                    )
                ),
            )
            .order_by(desc(SkillsMPSkill.effectiveness_score))
            .limit(limit)
        )

        skills = result.scalars().all()
        return [
            {
                "skill_id": str(s.id),
                "name": s.name,
                "description": s.description,
                "effectiveness": float(s.effectiveness_score),
                "why_recommended": f"High effectiveness ({s.effectiveness_score:.0f}%) with {s.usage_count} uses",
            }
            for s in skills
        ]

    async def continuous_learning_cycle(
        self,
        agent_id: str,
        recent_tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Run a continuous learning cycle for an agent.

        Analyzes recent tasks and identifies:
        - Skills that should be learned
        - Patterns in successful task completion
        - Gaps in agent's skill knowledge

        Args:
            agent_id: Agent identifier
            recent_tasks: List of recent task descriptions and outcomes

        Returns:
            Learning recommendations
        """
        all_learnings = []
        skills_to_learn = []

        for task in recent_tasks:
            task_desc = task.get("description", "")
            task_success = task.get("success", False)

            # Get skill recommendations for this task
            recs = await self.get_skills_for_task(
                agent_id=agent_id,
                task_description=task_desc,
                limit=3,
            )

            if not task_success and recs:
                # If task failed, strongly recommend learning these skills
                skills_to_learn.extend(recs)
                all_learnings.append(
                    {
                        "task": task_desc[:50],
                        "gap_identified": True,
                        "recommended_skills": [r["name"] for r in recs[:2]],
                    }
                )

        return {
            "agent_id": agent_id,
            "learning_opportunities": len(skills_to_learn),
            "recommended_skills": skills_to_learn[:5],
            "analysis": all_learnings[:3],
            "next_action": "Review recommended skills and apply them to similar future tasks",
        }


# Global bridge instance for agent access
_agent_skill_bridge: AgentSkillBridge | None = None


async def get_agent_skill_bridge(db: AsyncSession) -> AgentSkillBridge:
    """Get or create agent skill bridge instance."""
    global _agent_skill_bridge
    if _agent_skill_bridge is None:
        _agent_skill_bridge = AgentSkillBridge(db)
    return _agent_skill_bridge
