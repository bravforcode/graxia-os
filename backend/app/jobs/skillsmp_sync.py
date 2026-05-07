"""SkillsMP Hourly Sync Job with Merge Strategy"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.integrations.skillsmp_client import SkillData, SkillsMPClient
from app.models.skillsmp_skill import SkillLearningLog, SkillsMPSkill
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class SyncStats:
    """Statistics for a sync operation."""

    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    # By type
    by_type: dict[str, dict[str, int]] = field(default_factory=dict)

    # Totals
    total_added: int = 0
    total_updated: int = 0
    total_unchanged: int = 0
    total_errors: int = 0

    # Details
    errors: list[dict[str, Any]] = field(default_factory=list)

    def add_type_stats(
        self, skill_type: str, added: int = 0, updated: int = 0, unchanged: int = 0, errors: int = 0
    ):
        """Add stats for a skill type."""
        if skill_type not in self.by_type:
            self.by_type[skill_type] = {"added": 0, "updated": 0, "unchanged": 0, "errors": 0}

        self.by_type[skill_type]["added"] += added
        self.by_type[skill_type]["updated"] += updated
        self.by_type[skill_type]["unchanged"] += unchanged
        self.by_type[skill_type]["errors"] += errors

        self.total_added += added
        self.total_updated += updated
        self.total_unchanged += unchanged
        self.total_errors += errors

    def add_error(self, skill_id: str, error: str, skill_type: str = "unknown"):
        """Record an error."""
        self.errors.append(
            {
                "skill_id": skill_id,
                "error": error,
                "type": skill_type,
                "timestamp": datetime.now().isoformat(),
            }
        )
        self.total_errors += 1
        if skill_type not in self.by_type:
            self.by_type[skill_type] = {"added": 0, "updated": 0, "unchanged": 0, "errors": 0}
        self.by_type[skill_type]["errors"] += 1

    def complete(self):
        """Mark sync as complete."""
        self.completed_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        duration = None
        if self.completed_at:
            duration = (self.completed_at - self.started_at).total_seconds()

        return {
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": duration,
            "by_type": self.by_type,
            "total_added": self.total_added,
            "total_updated": self.total_updated,
            "total_unchanged": self.total_unchanged,
            "total_errors": self.total_errors,
            "total_processed": self.total_added + self.total_updated + self.total_unchanged,
            "errors": self.errors[:10] if self.errors else [],  # Limit error output
        }


class SkillsMPSyncJob:
    """
    Hourly sync job with merge strategy:
    - Add new skills
    - Update existing (preserve local improvements)
    - Never delete (mark as is_deleted_at_source only)
    """

    def __init__(self, db: AsyncSession, api_client: SkillsMPClient):
        self.db = db
        self.api = api_client
        self.stats = SyncStats()

    async def run(self, full_sync: bool = True) -> dict[str, Any]:
        """
        Run full sync cycle using search API.

        Args:
            full_sync: If True, sync all skills. If False, only check for updates.

        Returns:
            Sync statistics
        """
        try:
            logger.info("Starting SkillsMP sync job")

            # Fetch all skills using search queries
            all_skills = await self.api.fetch_all_skills(
                max_pages=5,  # Limit pages per query for performance
                per_page=100,
            )
            logger.info(f"Fetched {len(all_skills)} unique skills from API")

            # Process each skill
            type_stats: dict[str, dict] = {}

            for skill_data in all_skills:
                skill_type = skill_data.skill_type or "unknown"
                if skill_type not in type_stats:
                    type_stats[skill_type] = {"added": 0, "updated": 0, "unchanged": 0, "errors": 0}

                try:
                    result = await self._merge_skill(skill_data)
                    if result == "added":
                        type_stats[skill_type]["added"] += 1
                    elif result == "updated":
                        type_stats[skill_type]["updated"] += 1
                    else:
                        type_stats[skill_type]["unchanged"] += 1
                except Exception as e:
                    logger.error(f"Failed to merge skill {skill_data.id}: {e}")
                    self.stats.add_error(skill_data.id, str(e), skill_type)
                    type_stats[skill_type]["errors"] += 1

            # Add stats by type
            for skill_type, stats in type_stats.items():
                self.stats.add_type_stats(
                    skill_type,
                    stats["added"],
                    stats["updated"],
                    stats["unchanged"],
                    stats["errors"],
                )

            # Mark skills not updated in this sync as deleted at source
            await self._mark_deleted_skills()

            self.stats.complete()

            result = self.stats.to_dict()
            logger.info(
                f"SkillsMP sync completed: {result['total_processed']} processed, "
                f"{result['total_added']} added, {result['total_updated']} updated"
            )

            return {
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "stats": result,
            }

        except Exception as e:
            logger.exception("SkillsMP sync failed")
            self.stats.add_error("sync_job", str(e))
            return {
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "stats": self.stats.to_dict(),
            }

    # _sync_skill_type removed - now using search-based fetch_all_skills instead

    async def _merge_skill(self, skill_data: SkillData) -> str:
        """
        Merge single skill with merge logic.

        Returns:
            "added", "updated", or "unchanged"
        """
        # Check if exists
        result = await self.db.execute(
            select(SkillsMPSkill).where(SkillsMPSkill.external_id == skill_data.id)
        )
        existing = result.scalar_one_or_none()

        if not existing:
            # Create new skill
            new_skill = SkillsMPSkill(
                external_id=skill_data.id,
                source_type=skill_data.skill_type,
                name=skill_data.name,
                description=skill_data.description,
                content=skill_data.content,
                skill_metadata=skill_data.metadata,
                context_tags=skill_data.tags,
                trigger_patterns=skill_data.triggers,
                first_synced_at=datetime.now(),
                last_synced_at=datetime.now(),
                is_deleted_at_source=False,
                version=skill_data.version,
            )
            self.db.add(new_skill)
            await self.db.flush()

            # Log creation
            self.db.add(
                SkillLearningLog(
                    skill_id=new_skill.id,
                    learning_type="creation",
                    context="Synced from SkillsMP API",
                    after_state={"external_id": skill_data.id, "name": skill_data.name},
                    confidence_score=1.0,
                )
            )

            await self.db.commit()
            return "added"

        else:
            # Merge - only update if content changed and no local improvements
            content_changed = skill_data.content != existing.content
            has_ai_improvement = bool(existing.ai_improved_version)
            version_changed = skill_data.version != existing.version

            needs_update = (content_changed or version_changed) and not has_ai_improvement

            if needs_update:
                # Archive current version
                existing.archive_current_version()

                # Update fields
                existing.name = skill_data.name
                existing.description = skill_data.description
                existing.content = skill_data.content
                existing.metadata = {**existing.metadata, **skill_data.metadata}
                existing.context_tags = skill_data.tags
                existing.trigger_patterns = skill_data.triggers
                existing.version = skill_data.version
                existing.last_synced_at = datetime.now()
                existing.is_deleted_at_source = False
                existing.updated_at = datetime.now()

                # Log update
                self.db.add(
                    SkillLearningLog(
                        skill_id=existing.id,
                        learning_type="sync_update",
                        context=f"Updated from SkillsMP API (version {skill_data.version})",
                        before_state={"version": existing.version - 1},
                        after_state={"version": existing.version},
                        confidence_score=0.9,
                    )
                )

                await self.db.commit()
                return "updated"
            else:
                # Just update sync timestamp
                existing.last_synced_at = datetime.now()
                existing.is_deleted_at_source = False
                await self.db.commit()
                return "unchanged"

    async def _mark_deleted_skills(self) -> None:
        """Mark skills not found in last sync as deleted at source."""
        # Find skills not synced in last 2 hours
        two_hours_ago = datetime.now() - timedelta(hours=2)

        result = await self.db.execute(
            update(SkillsMPSkill)
            .where(SkillsMPSkill.last_synced_at < two_hours_ago)
            .where(not SkillsMPSkill.is_deleted_at_source)
            .where(SkillsMPSkill.auto_sync_enabled)
            .values(is_deleted_at_source=True)
            .returning(SkillsMPSkill.id, SkillsMPSkill.external_id)
        )

        marked_deleted = result.all()

        if marked_deleted:
            logger.info(f"Marked {len(marked_deleted)} skills as deleted at source")

            # Log deletions
            for row in marked_deleted:
                self.db.add(
                    SkillLearningLog(
                        skill_id=row.id,
                        learning_type="deletion_marked",
                        context="Skill no longer available at SkillsMP source",
                        confidence_score=1.0,
                    )
                )

            await self.db.commit()


async def run_hourly_sync(db: AsyncSession, api_key: str) -> dict[str, Any]:
    """
    Convenience function to run hourly sync.

    Usage:
        from app.jobs.skillsmp_sync import run_hourly_sync

        async with AsyncSessionLocal() as db:
            result = await run_hourly_sync(db, settings.SKILLSMP_API_KEY)
    """
    from app.integrations.skillsmp_client import SkillsMPConfig

    config = SkillsMPConfig(api_key=api_key)

    async with SkillsMPClient(config) as client:
        job = SkillsMPSyncJob(db, client)
        return await job.run()
