"""
Draft Command and Query Handlers
"""
import logging
from datetime import UTC, datetime

from app.core.result import Result, err, ok
from app.cqrs.commands import ApproveDraftCommand, RejectDraftCommand
from app.cqrs.handlers import CommandHandler, QueryHandler
from app.cqrs.queries import GetDraftQuery, ListDraftsQuery
from app.core.unit_of_work import AsyncUnitOfWork
from app.models.content_draft import ContentDraft
from app.repositories.draft_repository import DraftRepository

logger = logging.getLogger(__name__)


# Command Handlers
class ApproveDraftHandler(CommandHandler[ApproveDraftCommand, ContentDraft]):
    """Handler for approving drafts."""
    
    async def handle(self, command: ApproveDraftCommand) -> Result[ContentDraft, Exception]:
        """Approve draft."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = DraftRepository(session)
                
                # Get draft
                draft = await repo.get_by_id(command.draft_id)
                if not draft:
                    return err(ValueError(f"Draft not found: {command.draft_id}"))
                
                # Update status
                draft.status = "approved"
                draft.approved_at = datetime.now(UTC)
                draft.updated_at = datetime.now(UTC)
                
                # Save
                draft = await repo.update(draft)

                
                # Mark approvals resolved
                from app.core.control_plane import mark_subject_approvals_resolved
                await mark_subject_approvals_resolved("content_draft", command.draft_id, "approved")
                
                # Emit event
                from app.core.event_bus import event_bus
                await event_bus.emit("draft.approved", {
                    "draft_id": str(draft.id),
                    "draft_type": draft.type,
                })
                
                logger.info(f"Approved draft: {draft.id}")
                return ok(draft)
                
        except Exception as e:
            logger.error(f"Failed to approve draft: {e}")
            return err(e)


class RejectDraftHandler(CommandHandler[RejectDraftCommand, ContentDraft]):
    """Handler for rejecting drafts."""
    
    async def handle(self, command: RejectDraftCommand) -> Result[ContentDraft, Exception]:
        """Reject draft."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = DraftRepository(session)
                
                # Get draft
                draft = await repo.get_by_id(command.draft_id)
                if not draft:
                    return err(ValueError(f"Draft not found: {command.draft_id}"))
                
                # Update status
                draft.status = "rejected"
                draft.rejection_reason = command.reason
                draft.updated_at = datetime.now(UTC)
                
                # Save
                draft = await repo.update(draft)

                
                # Mark approvals resolved
                from app.core.control_plane import mark_subject_approvals_resolved
                await mark_subject_approvals_resolved(
                    "content_draft",
                    command.draft_id,
                    "rejected",
                    note=command.reason or None
                )
                
                logger.info(f"Rejected draft: {draft.id}")
                return ok(draft)
                
        except Exception as e:
            logger.error(f"Failed to reject draft: {e}")
            return err(e)


# Query Handlers
class GetDraftHandler(QueryHandler[GetDraftQuery, ContentDraft]):
    """Handler for getting draft by ID."""
    
    async def handle(self, query: GetDraftQuery) -> Result[ContentDraft, Exception]:
        """Get draft."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = DraftRepository(session)
                draft = await repo.get_by_id(query.draft_id)
                
                if not draft:
                    return err(ValueError(f"Draft not found: {query.draft_id}"))
                
                return ok(draft)
                
        except Exception as e:
            logger.error(f"Failed to get draft: {e}")
            return err(e)


class ListDraftsHandler(QueryHandler[ListDraftsQuery, list]):
    """Handler for listing drafts."""
    
    async def handle(self, query: ListDraftsQuery) -> Result[list, Exception]:
        """List drafts."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = DraftRepository(session)
                
                # Get drafts
                if query.status:
                    drafts = await repo.find_by_status(query.status, query.limit)
                else:
                    drafts = await repo.get_all(query.skip, query.limit)
                
                return ok(drafts)
                
        except Exception as e:
            logger.error(f"Failed to list drafts: {e}")
            return err(e)
