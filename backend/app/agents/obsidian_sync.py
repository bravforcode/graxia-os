"""
Obsidian sync agent for the shared second-brain vault.
"""
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from structlog import get_logger

import app.database as database
from app.agents.base import BaseAgent
from app.core.identity import identity
from app.integrations.obsidian import get_obsidian
from app.models.assistant_task import AssistantTask
from app.models.contact import Contact
from app.models.knowledge import KnowledgeItem
from app.models.opportunity import Opportunity
from app.models.skill_profile import SkillProfile
from app.models.submission import Submission

logger = get_logger(__name__)


def _coerce_uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


class ObsidianSyncAgent(BaseAgent):
    name = "obsidian_sync"

    async def bootstrap_second_brain(self) -> dict[str, Any]:
        obsidian = await get_obsidian()
        profile = identity.get_profile()
        skill_inventory = await self._load_skill_inventory()
        result = await obsidian.bootstrap_second_brain(
            profile=profile,
            skill_inventory=skill_inventory,
        )
        synced_entities = await self._sync_recent_entities()
        knowledge_count = await self.sync_knowledge_library()
        return {
            **result,
            "knowledge_count": knowledge_count,
            "synced_entities": synced_entities,
        }

    async def capture_context(
        self,
        project_key: str,
        title: str,
        summary: str,
        details: str,
        tags: list[str] | None = None,
        source_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        obsidian = await get_obsidian()
        path = await obsidian.capture_context_note(
            project_key=project_key,
            title=title,
            summary=summary,
            details=details,
            tags=tags,
            source_url=source_url,
            metadata=metadata,
        )
        return str(path)

    async def sync_skill_library(self) -> int:
        obsidian = await get_obsidian()
        profile = identity.get_profile()
        skill_inventory = await self._load_skill_inventory()
        result = await obsidian.sync_skill_inventory(
            skill_inventory=skill_inventory,
            projects=[item for item in profile.get("projects", []) if isinstance(item, dict)],
        )
        return int(result["skill_count"])

    async def sync_opportunity(self, opportunity_id: str) -> None:
        try:
            obsidian = await get_obsidian()
            async with database.AsyncSessionLocal() as db:
                opportunity = await db.get(Opportunity, _coerce_uuid(opportunity_id))
                if not opportunity:
                    logger.warning("opportunity_not_found", opp_id=opportunity_id)
                    return

                await obsidian.log_opportunity(
                    {
                        "id": str(opportunity.id),
                        "title": opportunity.title,
                        "source_platform": opportunity.source_platform,
                        "source_url": opportunity.source_url,
                        "description": opportunity.description,
                        "score": float(opportunity.total_score)
                        if opportunity.total_score is not None
                        else None,
                        "scoring_rationale": opportunity.scoring_rationale,
                        "status": opportunity.status,
                        "deadline": opportunity.deadline.isoformat()
                        if opportunity.deadline
                        else None,
                        "action_priority": opportunity.action_priority,
                        "tags": list(opportunity.tags or []),
                        "raw_data": opportunity.raw_data or {},
                    }
                )
        except Exception as exc:
            logger.error("obsidian_sync_failed", error=str(exc), opp_id=opportunity_id)

    async def sync_submission(self, submission_id: str) -> None:
        try:
            obsidian = await get_obsidian()
            async with database.AsyncSessionLocal() as db:
                submission = await db.get(Submission, _coerce_uuid(submission_id))
                if not submission:
                    logger.warning("submission_not_found", sub_id=submission_id)
                    return

                await obsidian.log_submission(
                    {
                        "id": str(submission.id),
                        "title": submission.title or "Untitled",
                        "opportunity_id": str(submission.opportunity_id)
                        if submission.opportunity_id
                        else None,
                        "sent_at": _iso_datetime(submission.sent_at),
                        "status": submission.status,
                        "proposal_text": submission.content,
                        "content": submission.content,
                        "outcome": submission.outcome_notes,
                        "outcome_notes": submission.outcome_notes,
                    }
                )
        except Exception as exc:
            logger.error("obsidian_sync_failed", error=str(exc), sub_id=submission_id)

    async def sync_contact(self, contact_id: str) -> None:
        try:
            obsidian = await get_obsidian()
            async with database.AsyncSessionLocal() as db:
                contact = await db.get(Contact, _coerce_uuid(contact_id))
                if not contact:
                    logger.warning("contact_not_found", contact_id=contact_id)
                    return

                await obsidian.create_contact_note(
                    {
                        "id": str(contact.id),
                        "name": contact.name,
                        "email": contact.email,
                        "company": contact.company,
                        "role": contact.role,
                        "linkedin_url": contact.linkedin_url,
                        "last_contacted_at": contact.last_contacted_at.isoformat()
                        if contact.last_contacted_at
                        else None,
                        "relationship_strength": contact.relationship_strength,
                        "notes": contact.notes,
                        "conversation_summary": contact.conversation_summary,
                    }
                )
        except Exception as exc:
            logger.error("obsidian_sync_failed", error=str(exc), contact_id=contact_id)

    async def sync_task(self, task_id: str) -> None:
        try:
            obsidian = await get_obsidian()
            async with database.AsyncSessionLocal() as db:
                task = await db.get(AssistantTask, _coerce_uuid(task_id))
                if not task:
                    logger.warning("task_not_found", task_id=task_id)
                    return

                await obsidian.log_task(
                    {
                        "id": str(task.id),
                        "title": task.title,
                        "description": task.description,
                        "task_type": task.task_type,
                        "priority": task.priority,
                        "status": task.status,
                        "due_date": _iso_datetime(task.due_date),
                        "assigned_to": task.assigned_to,
                        "related_entity_type": task.related_entity_type,
                        "related_entity_id": str(task.related_entity_id)
                        if task.related_entity_id
                        else None,
                    }
                )
        except Exception as exc:
            logger.error("obsidian_sync_failed", error=str(exc), task_id=task_id)

    async def sync_knowledge_item(self, knowledge_item_id: str) -> None:
        try:
            obsidian = await get_obsidian()
            async with database.AsyncSessionLocal() as db:
                item = await db.get(KnowledgeItem, _coerce_uuid(knowledge_item_id))
                if not item:
                    logger.warning("knowledge_item_not_found", knowledge_item_id=knowledge_item_id)
                    return

                await obsidian.log_knowledge_item(
                    {
                        "id": str(item.id),
                        "category": item.category,
                        "title": item.title,
                        "content": item.content,
                        "tags": list(item.tags or []),
                    }
                )
        except Exception as exc:
            logger.error(
                "obsidian_sync_failed",
                error=str(exc),
                knowledge_item_id=knowledge_item_id,
            )

    async def sync_knowledge_library(self) -> int:
        count = 0
        async with database.AsyncSessionLocal() as db:
            result = await db.execute(
                select(KnowledgeItem)
                .where(KnowledgeItem.is_active.is_(True))
                .order_by(desc(KnowledgeItem.updated_at))
                .limit(50)
            )
            for item in result.scalars().all():
                await self.sync_knowledge_item(str(item.id))
                count += 1
        return count

    async def create_daily_note(self) -> None:
        try:
            obsidian = await get_obsidian()
            await obsidian.create_daily_note()
            logger.info("daily_note_created")
        except Exception as exc:
            logger.error("daily_note_creation_failed", error=str(exc))

    async def create_weekly_review(self, review_data: dict[str, Any] | None = None) -> None:
        try:
            obsidian = await get_obsidian()
            now = datetime.now(UTC)
            week_start = now - timedelta(days=now.weekday())
            await obsidian.create_weekly_review(week_start, review_data=review_data)
            logger.info("weekly_review_created")
        except Exception as exc:
            logger.error("weekly_review_creation_failed", error=str(exc))

    async def handle_opportunity_found(self, payload: dict[str, Any]) -> None:
        opportunity_id = payload.get("opportunity_id") or payload.get("aggregate_id")
        if opportunity_id:
            await self.sync_opportunity(str(opportunity_id))

    async def handle_submission_sent(self, payload: dict[str, Any]) -> None:
        submission_id = payload.get("submission_id") or payload.get("aggregate_id")
        if submission_id:
            await self.sync_submission(str(submission_id))

    async def handle_contact_created(self, payload: dict[str, Any]) -> None:
        contact_id = payload.get("contact_id")
        if contact_id:
            await self.sync_contact(str(contact_id))

    async def handle_task_created(self, payload: dict[str, Any]) -> None:
        task_id = payload.get("task_id")
        if task_id:
            await self.sync_task(str(task_id))

    async def handle_knowledge_captured(self, payload: dict[str, Any]) -> None:
        knowledge_item_id = payload.get("knowledge_item_id")
        if knowledge_item_id:
            await self.sync_knowledge_item(str(knowledge_item_id))

    async def _load_skill_inventory(self) -> list[dict[str, Any]]:
        async with database.AsyncSessionLocal() as db:
            result = await db.execute(
                select(SkillProfile)
                .where(SkillProfile.is_active.is_(True))
                .order_by(SkillProfile.category, SkillProfile.name)
            )
            rows = result.scalars().all()
            if rows:
                return [
                    {
                        "name": row.name,
                        "category": row.category,
                        "level": row.level,
                        "years_experience": float(row.years_experience)
                        if row.years_experience is not None
                        else None,
                        "evidence": list(row.evidence or []),
                    }
                    for row in rows
                ]

        profile = identity.get_profile()
        technical = [
            item for item in profile.get("skills", {}).get("technical", []) if isinstance(item, dict)
        ]
        soft = [
            {"name": item, "category": "soft", "level": "unknown", "years_experience": None, "evidence": []}
            for item in profile.get("skills", {}).get("soft", [])
            if isinstance(item, str)
        ]
        return [
            {
                "name": skill.get("name"),
                "category": "technical",
                "level": skill.get("level"),
                "years_experience": skill.get("years"),
                "evidence": [],
            }
            for skill in technical
        ] + soft

    async def _sync_recent_entities(self) -> dict[str, int]:
        counts = {"opportunities": 0, "submissions": 0, "contacts": 0, "tasks": 0}
        async with database.AsyncSessionLocal() as db:
            recent_opportunities = (
                await db.execute(
                    select(Opportunity)
                    .where(Opportunity.is_deleted.is_(False))
                    .order_by(desc(Opportunity.updated_at), desc(Opportunity.found_at))
                    .limit(25)
                )
            ).scalars().all()
            for opportunity in recent_opportunities:
                await self.sync_opportunity(str(opportunity.id))
                counts["opportunities"] += 1

            recent_submissions = (
                await db.execute(
                    select(Submission)
                    .where(Submission.is_deleted.is_(False))
                    .order_by(desc(Submission.updated_at), desc(Submission.created_at))
                    .limit(25)
                )
            ).scalars().all()
            for submission in recent_submissions:
                await self.sync_submission(str(submission.id))
                counts["submissions"] += 1

            contacts = (
                await db.execute(
                    select(Contact)
                    .where(Contact.is_deleted.is_(False))
                    .order_by(desc(Contact.updated_at), desc(Contact.created_at))
                    .limit(50)
                )
            ).scalars().all()
            for contact in contacts:
                await self.sync_contact(str(contact.id))
                counts["contacts"] += 1

            open_tasks = (
                await db.execute(
                    select(AssistantTask)
                    .where(AssistantTask.status != "completed")
                    .order_by(desc(AssistantTask.updated_at), desc(AssistantTask.priority))
                    .limit(50)
                )
            ).scalars().all()
            for task in open_tasks:
                await self.sync_task(str(task.id))
                counts["tasks"] += 1

        return counts

    async def test_obsidian_connection(self) -> bool:
        """Test connection to Obsidian vault and API."""
        try:
            # Test vault path exists
            from pathlib import Path
            vault_path = Path(settings.OBSIDIAN_VAULT_PATH)
            if not vault_path.exists():
                logger.error(f"Vault path does not exist: {vault_path}")
                return False

            # Test API connection
            obsidian = await get_obsidian()
            if obsidian:
                logger.info("Obsidian API connection successful")
                return True
            else:
                logger.error("Obsidian API connection failed")
                return False

        except Exception as e:
            logger.error(f"Obsidian connection test failed: {e}")
            return False


obsidian_sync_agent = ObsidianSyncAgent()
