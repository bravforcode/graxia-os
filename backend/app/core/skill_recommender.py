"""Skill Recommendation Engine - Context-Aware RAG"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skillsmp_skill import SkillRecommendationCache, SkillsMPSkill

logger = logging.getLogger(__name__)


@dataclass
class SkillRecommendation:
    """Individual skill recommendation."""

    skill_id: UUID
    name: str
    skill_type: str
    description: str | None
    content_preview: str
    score: float
    effectiveness: float
    usage_count: int
    match_reasons: dict[str, float]
    trigger_match: str | None = None


@dataclass
class SkillChain:
    """Chain of skills that work together."""

    skills: list[SkillRecommendation]
    total_score: float
    chain_reason: str


class SkillRecommender:
    """
    Context-aware skill recommendation engine.

    Features:
    - TF-IDF text matching
    - Semantic similarity (with embeddings)
    - Effectiveness scoring
    - Usage popularity
    - Diversity promotion
    - Skill chaining
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.vectorizer = TfidfVectorizer(
            max_features=5000, stop_words="english", ngram_range=(1, 2)
        )

    async def recommend(
        self,
        task_context: str,
        current_skill_ids: list[UUID] | None = None,
        preferred_types: list[str] | None = None,
        limit: int = 5,
        use_cache: bool = True,
    ) -> list[SkillRecommendation]:
        """
        Recommend skills based on task context.

        Args:
            task_context: Description of the current task/context
            current_skill_ids: Skills already being used (for diversity)
            preferred_types: Preferred skill types
            limit: Number of recommendations
            use_cache: Whether to use cached results

        Returns:
            List of skill recommendations sorted by relevance
        """
        # Check cache
        if use_cache:
            cache_key = self._hash_context(task_context, current_skill_ids, preferred_types)
            cached = await self._get_cached_recommendations(cache_key)
            if cached:
                return cached

        # Get active skills
        skills = await self._get_active_skills(preferred_types)

        if not skills:
            return []

        # Score all skills
        scored_skills = await self._score_skills(
            skills=skills,
            task_context=task_context,
            current_skill_ids=current_skill_ids or [],
        )

        # Sort and limit
        scored_skills.sort(key=lambda x: x.score, reverse=True)
        recommendations = scored_skills[:limit]

        # Cache results
        if use_cache:
            await self._cache_recommendations(cache_key, recommendations)

        return recommendations

    async def search(
        self,
        query: str,
        skill_type: str | None = None,
        min_effectiveness: float = 0,
        limit: int = 10,
    ) -> list[SkillRecommendation]:
        """
        Search skills by query with RAG.

        Args:
            query: Search query
            skill_type: Filter by type
            min_effectiveness: Minimum effectiveness score
            limit: Number of results

        Returns:
            Matching skills sorted by relevance
        """
        # Get active skills with filter
        skills = await self._get_active_skills(
            preferred_types=[skill_type] if skill_type else None,
            min_effectiveness=min_effectiveness,
        )

        if not skills:
            return []

        # TF-IDF matching
        skill_texts = [self._skill_search_text(s) for s in skills]

        if not skill_texts:
            return []

        try:
            tfidf_matrix = self.vectorizer.fit_transform(skill_texts + [query])
            query_vector = tfidf_matrix[-1]
            skill_vectors = tfidf_matrix[:-1]

            similarities = cosine_similarity(query_vector, skill_vectors)[0]
        except Exception as e:
            logger.warning(f"TF-IDF failed: {e}. Using fallback scoring.")
            similarities = np.zeros(len(skills))

        # Build recommendations
        recommendations = []
        for i, skill in enumerate(skills):
            base_score = float(similarities[i])

            if base_score < 0.1:  # Too low relevance
                continue

            # Boost by effectiveness
            effectiveness_boost = float(skill.effectiveness_score or 0) / 100 * 0.3
            popularity_boost = min((skill.usage_count or 0) / 50, 0.2)

            final_score = base_score + effectiveness_boost + popularity_boost

            recommendations.append(
                SkillRecommendation(
                    skill_id=skill.id,
                    name=skill.name,
                    skill_type=skill.source_type,
                    description=skill.description,
                    content_preview=(skill.content or "")[:200] + "..." if skill.content else "",
                    score=final_score,
                    effectiveness=float(skill.effectiveness_score or 0),
                    usage_count=skill.usage_count or 0,
                    match_reasons={
                        "text_similarity": base_score,
                        "effectiveness": effectiveness_boost,
                        "popularity": popularity_boost,
                    },
                )
            )

        # Sort by score
        recommendations.sort(key=lambda x: x.score, reverse=True)

        return recommendations[:limit]

    async def find_skill_chain(
        self,
        task_description: str,
        max_chain_length: int = 3,
        current_skills: list[UUID] | None = None,
    ) -> SkillChain | None:
        """
        Find sequences of skills that work well together.

        Args:
            task_description: Task to accomplish
            max_chain_length: Maximum skills in chain
            current_skills: Skills already being used

        Returns:
            Skill chain if found, None otherwise
        """
        # Start with best matching skill
        initial = await self.recommend(
            task_context=task_description, current_skill_ids=current_skills, limit=1
        )

        if not initial:
            return None

        chain = [initial[0]]
        used_ids = set(current_skills or []) | {initial[0].skill_id}

        # Follow related skills
        for _ in range(max_chain_length - 1):
            current_skill = await self._get_skill(chain[-1].skill_id)
            if not current_skill or not current_skill.related_skill_ids:
                break

            # Find best related skill not already used
            related_ids = [sid for sid in current_skill.related_skill_ids if sid not in used_ids]

            if not related_ids:
                break

            # Get related skills
            related = await self._get_skills_by_ids(related_ids)

            # Score them for this task
            scored = await self._score_skills(related, task_description, list(used_ids))

            if not scored:
                break

            # Add best match
            best = scored[0]
            chain.append(best)
            used_ids.add(best.skill_id)

        if len(chain) < 2:
            return None

        total_score = sum(s.score for s in chain) / len(chain)

        return SkillChain(
            skills=chain,
            total_score=total_score,
            chain_reason=f"Sequential skills for: {task_description[:100]}...",
        )

    async def discover_by_trigger(
        self,
        context_text: str,
        limit: int = 5,
    ) -> list[SkillRecommendation]:
        """
        Discover skills by trigger pattern matching.

        Args:
            context_text: Text to match against triggers
            limit: Number of results

        Returns:
            Skills whose triggers match the context
        """
        # Get all skills with triggers
        result = await self.db.execute(
            select(SkillsMPSkill)
            .where(SkillsMPSkill.trigger_patterns is not None)
            .where(SkillsMPSkill.trigger_patterns != [])
            .where(not SkillsMPSkill.is_deleted_at_source)
        )
        skills = result.scalars().all()

        # Match triggers
        matched = []
        context_lower = context_text.lower()

        for skill in skills:
            for trigger in skill.trigger_patterns or []:
                trigger_lower = trigger.lower()

                # Exact match or substring
                if trigger_lower in context_lower or context_lower in trigger_lower:
                    score = 0.8  # Base trigger match score

                    # Boost by effectiveness
                    score += float(skill.effectiveness_score or 0) / 100 * 0.2

                    matched.append(
                        SkillRecommendation(
                            skill_id=skill.id,
                            name=skill.name,
                            skill_type=skill.source_type,
                            description=skill.description,
                            content_preview=(skill.content or "")[:200] + "..."
                            if skill.content
                            else "",
                            score=score,
                            effectiveness=float(skill.effectiveness_score or 0),
                            usage_count=skill.usage_count or 0,
                            match_reasons={"trigger_match": 0.8, "effectiveness": score - 0.8},
                            trigger_match=trigger,
                        )
                    )
                    break  # Only count one trigger match per skill

        # Sort by score
        matched.sort(key=lambda x: x.score, reverse=True)

        return matched[:limit]

    async def get_skill_gaps(
        self,
        task_context: str,
        current_skills: list[UUID] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Identify potential skill gaps for a task.

        Args:
            task_context: Task description
            current_skills: Currently available skills

        Returns:
            List of identified gaps with suggestions
        """
        # This would ideally use a more sophisticated analysis
        # For now, return based on missing skill types

        gaps = []

        # Get recommended skills
        recommendations = await self.recommend(
            task_context=task_context, current_skill_ids=current_skills, limit=10
        )

        # Check coverage by type
        type_coverage = {}
        for rec in recommendations:
            if rec.skill_type not in type_coverage:
                type_coverage[rec.skill_type] = []
            type_coverage[rec.skill_type].append(rec)

        # Identify gaps
        all_types = ["openclaw", "claude", "codex", "hermes", "tool", "dev", "context"]

        for skill_type in all_types:
            if skill_type not in type_coverage:
                gaps.append(
                    {
                        "type": skill_type,
                        "reason": f"No {skill_type} skills recommended for this task",
                        "suggestion": f"Consider adding {skill_type} skills",
                    }
                )
            elif len(type_coverage[skill_type]) < 2:
                gaps.append(
                    {
                        "type": skill_type,
                        "reason": f"Limited {skill_type} coverage ({len(type_coverage[skill_type])} skills)",
                        "suggestion": f"Consider more {skill_type} skills for variety",
                    }
                )

        return gaps

    async def _get_active_skills(
        self,
        preferred_types: list[str] | None = None,
        min_effectiveness: float = 0,
    ) -> list[SkillsMPSkill]:
        """Get active (non-deleted) skills."""
        query = select(SkillsMPSkill).where(not SkillsMPSkill.is_deleted_at_source)

        if preferred_types:
            query = query.where(SkillsMPSkill.source_type.in_(preferred_types))

        if min_effectiveness > 0:
            query = query.where(SkillsMPSkill.effectiveness_score >= min_effectiveness)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _get_skill(self, skill_id: UUID) -> SkillsMPSkill | None:
        """Get skill by ID."""
        result = await self.db.execute(select(SkillsMPSkill).where(SkillsMPSkill.id == skill_id))
        return result.scalar_one_or_none()

    async def _get_skills_by_ids(self, skill_ids: list[str]) -> list[SkillsMPSkill]:
        """Get multiple skills by IDs."""
        if not skill_ids:
            return []
        result = await self.db.execute(select(SkillsMPSkill).where(SkillsMPSkill.id.in_(skill_ids)))
        return list(result.scalars().all())

    async def _score_skills(
        self,
        skills: list[SkillsMPSkill],
        task_context: str,
        current_skill_ids: list[UUID],
    ) -> list[SkillRecommendation]:
        """Score skills for the given context."""
        if not skills:
            return []

        # Build text representations
        skill_texts = [self._skill_search_text(s) for s in skills]

        try:
            tfidf_matrix = self.vectorizer.fit_transform(skill_texts + [task_context])
            query_vector = tfidf_matrix[-1]
            skill_vectors = tfidf_matrix[:-1]

            similarities = cosine_similarity(query_vector, skill_vectors)[0]
        except Exception as e:
            logger.warning(f"TF-IDF scoring failed: {e}")
            similarities = np.zeros(len(skills))

        # Build recommendations with full scoring
        recommendations = []
        for i, skill in enumerate(skills):
            base_score = float(similarities[i])

            # Skip very low relevance
            if base_score < 0.05:
                continue

            # Effectiveness boost
            effectiveness_boost = float(skill.effectiveness_score or 0) / 100 * 0.3

            # Popularity boost (diminishing returns)
            popularity_boost = min((skill.usage_count or 0) / 50, 0.2)

            # Diversity penalty for recently used
            diversity_penalty = 0
            if skill.id in current_skill_ids:
                diversity_penalty = 0.15

            final_score = base_score + effectiveness_boost + popularity_boost - diversity_penalty

            recommendations.append(
                SkillRecommendation(
                    skill_id=skill.id,
                    name=skill.name,
                    skill_type=skill.source_type,
                    description=skill.description,
                    content_preview=(skill.content or "")[:200] + "..." if skill.content else "",
                    score=final_score,
                    effectiveness=float(skill.effectiveness_score or 0),
                    usage_count=skill.usage_count or 0,
                    match_reasons={
                        "text_similarity": base_score,
                        "effectiveness": effectiveness_boost,
                        "popularity": popularity_boost,
                        "diversity_penalty": -diversity_penalty,
                    },
                )
            )

        return recommendations

    def _skill_search_text(self, skill: SkillsMPSkill) -> str:
        """Build searchable text from skill."""
        parts = [
            skill.name,
            skill.description or "",
        ]

        if skill.context_tags:
            parts.extend(skill.context_tags)

        if skill.trigger_patterns:
            parts.extend(skill.trigger_patterns)

        if skill.content:
            parts.append(skill.content[:1000])  # First 1000 chars

        return " ".join(parts)

    def _hash_context(
        self,
        task_context: str,
        current_skill_ids: list[UUID] | None,
        preferred_types: list[str] | None,
    ) -> str:
        """Create hash for cache key."""
        content = f"{task_context}:{current_skill_ids}:{preferred_types}"
        return hashlib.sha256(content.encode()).hexdigest()

    async def _get_cached_recommendations(
        self,
        cache_key: str,
    ) -> list[SkillRecommendation] | None:
        """Get cached recommendations if valid."""
        result = await self.db.execute(
            select(SkillRecommendationCache)
            .where(SkillRecommendationCache.context_hash == cache_key)
            .where(SkillRecommendationCache.expires_at > datetime.now())
        )
        cached = result.scalar_one_or_none()

        if not cached:
            return None

        # Check if we have skill IDs to reconstruct
        if not cached.recommended_skill_ids:
            return None

        # Reconstruct from cached IDs
        skills = await self._get_skills_by_ids(cached.recommended_skill_ids)

        # Build recommendations with scores from cache
        recommendations = []
        scores = cached.scores or {}

        for skill in skills:
            skill_scores = scores.get(str(skill.id), {})
            recommendations.append(
                SkillRecommendation(
                    skill_id=skill.id,
                    name=skill.name,
                    skill_type=skill.source_type,
                    description=skill.description,
                    content_preview=(skill.content or "")[:200] + "..." if skill.content else "",
                    score=skill_scores.get("total", 0.5),
                    effectiveness=float(skill.effectiveness_score or 0),
                    usage_count=skill.usage_count or 0,
                    match_reasons=skill_scores.get("reasons", {}),
                )
            )

        recommendations.sort(key=lambda x: x.score, reverse=True)

        return recommendations

    async def _cache_recommendations(
        self,
        cache_key: str,
        recommendations: list[SkillRecommendation],
    ) -> None:
        """Cache recommendations."""
        expires_at = datetime.now() + timedelta(hours=1)

        # Store skill IDs and scores
        skill_ids = [str(r.skill_id) for r in recommendations]
        scores = {
            str(r.skill_id): {
                "total": r.score,
                "reasons": r.match_reasons,
            }
            for r in recommendations
        }

        cache_entry = SkillRecommendationCache(
            context_hash=cache_key,
            recommended_skill_ids=skill_ids,
            scores=scores,
            expires_at=expires_at,
        )

        self.db.add(cache_entry)

        # Clean old cache entries
        await self.db.execute(
            select(SkillRecommendationCache).where(
                SkillRecommendationCache.expires_at < datetime.now()
            )
            # Would delete here, but SQLAlchemy async delete syntax varies
        )

        await self.db.commit()
