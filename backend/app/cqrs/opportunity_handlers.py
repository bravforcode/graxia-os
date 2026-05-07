"""
Opportunity Command and Query Handlers
"""
import logging
from datetime import UTC, datetime
from uuid import uuid4

from app.core.result import Result, err, ok
from app.core.specifications import HighScoreOpportunity, UrgentOpportunity
from app.cqrs.commands import (
    ApproveOpportunityCommand,
    CreateOpportunityCommand,
    RejectOpportunityCommand,
    ScoreOpportunityCommand,
)
from app.cqrs.handlers import CommandHandler, QueryHandler
from app.cqrs.queries import (
    GetHighScoreOpportunitiesQuery,
    GetOpportunityQuery,
    GetUrgentOpportunitiesQuery,
    ListOpportunitiesQuery,
)
from app.core.unit_of_work import AsyncUnitOfWork
from app.models.opportunity import Opportunity
from app.repositories.opportunity_repository import OpportunityRepository

logger = logging.getLogger(__name__)


# Command Handlers
class CreateOpportunityHandler(CommandHandler[CreateOpportunityCommand, Opportunity]):
    """Handler for creating opportunities."""
    
    async def handle(self, command: CreateOpportunityCommand) -> Result[Opportunity, Exception]:
        """Create new opportunity."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = OpportunityRepository(session)
                
                # Create opportunity
                opportunity = Opportunity(
                    id=uuid4(),
                    title=command.title,
                    source=command.source,
                    url=command.url,
                    description=command.description,
                    deadline=command.deadline,
                    budget=command.budget,
                    status="new",
                    discovered_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                
                # Save
                opportunity = await repo.add(opportunity)

                
                # Emit event
                from app.core.event_bus import event_bus
                await event_bus.emit("opportunity.discovered", {
                    "opportunity_id": str(opportunity.id),
                    "title": opportunity.title,
                    "source": opportunity.source,
                })
                
                logger.info(f"Created opportunity: {opportunity.id}")
                return ok(opportunity)
                
        except Exception as e:
            logger.error(f"Failed to create opportunity: {e}")
            return err(e)


class ScoreOpportunityHandler(CommandHandler[ScoreOpportunityCommand, Opportunity]):
    """Handler for scoring opportunities."""
    
    async def handle(self, command: ScoreOpportunityCommand) -> Result[Opportunity, Exception]:
        """Score opportunity."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = OpportunityRepository(session)
                
                # Get opportunity
                opportunity = await repo.get_by_id(command.opportunity_id)
                if not opportunity:
                    return err(ValueError(f"Opportunity not found: {command.opportunity_id}"))
                
                # Trigger scoring (via agent)
                from app.core.event_bus import event_bus
                await event_bus.emit("opportunity.found", {
                    "opportunity_id": str(opportunity.id)
                })
                
                logger.info(f"Triggered scoring for opportunity: {opportunity.id}")
                return ok(opportunity)
                
        except Exception as e:
            logger.error(f"Failed to score opportunity: {e}")
            return err(e)


class ApproveOpportunityHandler(CommandHandler[ApproveOpportunityCommand, Opportunity]):
    """Handler for approving opportunities."""
    
    async def handle(self, command: ApproveOpportunityCommand) -> Result[Opportunity, Exception]:
        """Approve opportunity."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = OpportunityRepository(session)
                
                # Get opportunity
                opportunity = await repo.get_by_id(command.opportunity_id)
                if not opportunity:
                    return err(ValueError(f"Opportunity not found: {command.opportunity_id}"))
                
                # Update status
                opportunity.status = "approved"
                opportunity.decision = "approve"
                opportunity.updated_at = datetime.now(UTC)
                
                # Save
                opportunity = await repo.update(opportunity)

                
                # Emit event
                from app.core.event_bus import event_bus
                await event_bus.emit("opportunity.approved", {
                    "opportunity_id": str(opportunity.id),
                    "title": opportunity.title,
                })
                
                logger.info(f"Approved opportunity: {opportunity.id}")
                return ok(opportunity)
                
        except Exception as e:
            logger.error(f"Failed to approve opportunity: {e}")
            return err(e)


class RejectOpportunityHandler(CommandHandler[RejectOpportunityCommand, Opportunity]):
    """Handler for rejecting opportunities."""
    
    async def handle(self, command: RejectOpportunityCommand) -> Result[Opportunity, Exception]:
        """Reject opportunity."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = OpportunityRepository(session)
                
                # Get opportunity
                opportunity = await repo.get_by_id(command.opportunity_id)
                if not opportunity:
                    return err(ValueError(f"Opportunity not found: {command.opportunity_id}"))
                
                # Update status
                opportunity.status = "ignored"
                opportunity.decision = "skip"
                opportunity.updated_at = datetime.now(UTC)
                
                # Save
                opportunity = await repo.update(opportunity)

                
                # Emit event
                from app.core.event_bus import event_bus
                await event_bus.emit("opportunity.rejected", {
                    "opportunity_id": str(opportunity.id),
                    "title": opportunity.title,
                })
                
                logger.info(f"Rejected opportunity: {opportunity.id}")
                return ok(opportunity)
                
        except Exception as e:
            logger.error(f"Failed to reject opportunity: {e}")
            return err(e)


# Query Handlers
class GetOpportunityHandler(QueryHandler[GetOpportunityQuery, Opportunity]):
    """Handler for getting opportunity by ID."""
    
    async def handle(self, query: GetOpportunityQuery) -> Result[Opportunity, Exception]:
        """Get opportunity."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = OpportunityRepository(session)
                opportunity = await repo.get_by_id(query.opportunity_id)
                
                if not opportunity:
                    return err(ValueError(f"Opportunity not found: {query.opportunity_id}"))
                
                return ok(opportunity)
                
        except Exception as e:
            logger.error(f"Failed to get opportunity: {e}")
            return err(e)


class ListOpportunitiesHandler(QueryHandler[ListOpportunitiesQuery, list]):
    """Handler for listing opportunities."""
    
    async def handle(self, query: ListOpportunitiesQuery) -> Result[list, Exception]:
        """List opportunities."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = OpportunityRepository(session)
                
                # Get opportunities
                if query.status:
                    opportunities = await repo.find_by_status(query.status, query.limit)
                else:
                    opportunities = await repo.get_all(query.skip, query.limit)
                
                # Filter by score if specified
                if query.min_score:
                    opportunities = [
                        opp for opp in opportunities
                        if opp.total_score and opp.total_score >= query.min_score
                    ]
                
                return ok(opportunities)
                
        except Exception as e:
            logger.error(f"Failed to list opportunities: {e}")
            return err(e)


class GetHighScoreOpportunitiesHandler(QueryHandler[GetHighScoreOpportunitiesQuery, list]):
    """Handler for getting high-score opportunities."""
    
    async def handle(self, query: GetHighScoreOpportunitiesQuery) -> Result[list, Exception]:
        """Get high-score opportunities."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = OpportunityRepository(session)
                
                # Use specification
                spec = HighScoreOpportunity(threshold=query.threshold)
                opportunities = await repo.find(spec)
                
                # Limit results
                opportunities = opportunities[:query.limit]
                
                return ok(opportunities)
                
        except Exception as e:
            logger.error(f"Failed to get high-score opportunities: {e}")
            return err(e)


class GetUrgentOpportunitiesHandler(QueryHandler[GetUrgentOpportunitiesQuery, list]):
    """Handler for getting urgent opportunities."""
    
    async def handle(self, query: GetUrgentOpportunitiesQuery) -> Result[list, Exception]:
        """Get urgent opportunities."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = OpportunityRepository(session)
                
                # Use specification
                spec = UrgentOpportunity()
                opportunities = await repo.find(spec)
                
                # Limit results
                opportunities = opportunities[:query.limit]
                
                return ok(opportunities)
                
        except Exception as e:
            logger.error(f"Failed to get urgent opportunities: {e}")
            return err(e)
