"""
Submission Command and Query Handlers
"""
import logging
from datetime import UTC, datetime
from uuid import uuid4

from app.core.result import Result, err, ok
from app.cqrs.commands import (
    CreateSubmissionCommand,
    MarkSubmissionLostCommand,
    MarkSubmissionWonCommand,
)
from app.cqrs.handlers import CommandHandler, QueryHandler
from app.cqrs.queries import (
    GetSubmissionQuery,
    ListSubmissionsQuery,
)
from app.core.unit_of_work import AsyncUnitOfWork
from app.models.submission import Submission
from app.repositories.submission_repository import SubmissionRepository

logger = logging.getLogger(__name__)


# Command Handlers
class CreateSubmissionHandler(CommandHandler[CreateSubmissionCommand, Submission]):
    """Handler for creating submissions."""
    
    async def handle(self, command: CreateSubmissionCommand) -> Result[Submission, Exception]:
        """Create new submission."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = SubmissionRepository(session)
                
                # Create submission
                submission = Submission(
                    id=uuid4(),
                    opportunity_id=command.opportunity_id,
                    contact_id=command.contact_id,
                    type=command.type,
                    title=command.title,
                    status="draft",
                    content=command.content,
                    subject_line=command.subject_line,
                    proposed_value=command.proposed_value,
                    currency=command.currency or "THB",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                
                # Save
                submission = await repo.add(submission)

                
                # Emit event
                from app.core.event_bus import event_bus
                await event_bus.emit("submission.created", {
                    "submission_id": str(submission.id),
                    "opportunity_id": str(submission.opportunity_id) if submission.opportunity_id else None,
                    "type": submission.type,
                })
                
                logger.info(f"Created submission: {submission.id}")
                return ok(submission)
                
        except Exception as e:
            logger.error(f"Failed to create submission: {e}")
            return err(e)


class MarkSubmissionWonHandler(CommandHandler[MarkSubmissionWonCommand, Submission]):
    """Handler for marking submission as won."""
    
    async def handle(self, command: MarkSubmissionWonCommand) -> Result[Submission, Exception]:
        """Mark submission as won."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = SubmissionRepository(session)
                
                # Get submission
                submission = await repo.get_by_id(command.submission_id)
                if not submission:
                    return err(ValueError(f"Submission not found: {command.submission_id}"))
                
                # Update status
                submission.status = "won"
                submission.actual_value = command.actual_value
                submission.outcome_at = datetime.now(UTC)
                submission.updated_at = datetime.now(UTC)
                
                # Save
                submission = await repo.update(submission)

                
                # Emit event
                from app.core.event_bus import event_bus
                await event_bus.emit("submission.won", {
                    "submission_id": str(submission.id),
                    "actual_value_thb": float(submission.actual_value or 0),
                })
                
                logger.info(f"Marked submission as won: {submission.id}")
                return ok(submission)
                
        except Exception as e:
            logger.error(f"Failed to mark submission as won: {e}")
            return err(e)


class MarkSubmissionLostHandler(CommandHandler[MarkSubmissionLostCommand, Submission]):
    """Handler for marking submission as lost."""
    
    async def handle(self, command: MarkSubmissionLostCommand) -> Result[Submission, Exception]:
        """Mark submission as lost."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = SubmissionRepository(session)
                
                # Get submission
                submission = await repo.get_by_id(command.submission_id)
                if not submission:
                    return err(ValueError(f"Submission not found: {command.submission_id}"))
                
                # Update status
                submission.status = "lost"
                submission.lost_reason_primary = command.lost_reason
                submission.outcome_at = datetime.now(UTC)
                submission.updated_at = datetime.now(UTC)
                
                # Save
                submission = await repo.update(submission)

                
                # Emit event
                from app.core.event_bus import event_bus
                await event_bus.emit("submission.lost", {
                    "submission_id": str(submission.id),
                    "lost_reason": submission.lost_reason_primary,
                })
                
                logger.info(f"Marked submission as lost: {submission.id}")
                return ok(submission)
                
        except Exception as e:
            logger.error(f"Failed to mark submission as lost: {e}")
            return err(e)


# Query Handlers
class GetSubmissionHandler(QueryHandler[GetSubmissionQuery, Submission]):
    """Handler for getting submission by ID."""
    
    async def handle(self, query: GetSubmissionQuery) -> Result[Submission, Exception]:
        """Get submission."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = SubmissionRepository(session)
                submission = await repo.get_by_id(query.submission_id)
                
                if not submission:
                    return err(ValueError(f"Submission not found: {query.submission_id}"))
                
                return ok(submission)
                
        except Exception as e:
            logger.error(f"Failed to get submission: {e}")
            return err(e)


class ListSubmissionsHandler(QueryHandler[ListSubmissionsQuery, list]):
    """Handler for listing submissions."""
    
    async def handle(self, query: ListSubmissionsQuery) -> Result[list, Exception]:
        """List submissions."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = SubmissionRepository(session)
                
                # Get submissions
                if query.status:
                    submissions = await repo.find_by_status(query.status, query.limit)
                else:
                    submissions = await repo.get_all(query.skip, query.limit)
                
                return ok(submissions)
                
        except Exception as e:
            logger.error(f"Failed to list submissions: {e}")
            return err(e)
