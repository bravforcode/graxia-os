"""
CQRS Setup

Register all command and query handlers.
"""
import logging

from app.cqrs.commands import (
    ApproveDraftCommand,
    ApproveOpportunityCommand,
    CreateContactCommand,
    CreateOpportunityCommand,
    CreateSubmissionCommand,
    MarkSubmissionLostCommand,
    MarkSubmissionWonCommand,
    RejectDraftCommand,
    RejectOpportunityCommand,
    ScoreOpportunityCommand,
)
from app.cqrs.contact_handlers import (
    CreateContactHandler,
    GetContactHandler,
    ListContactsHandler,
)
from app.cqrs.draft_handlers import (
    ApproveDraftHandler,
    GetDraftHandler,
    ListDraftsHandler,
    RejectDraftHandler,
)
from app.cqrs.handlers import mediator
from app.cqrs.opportunity_handlers import (
    ApproveOpportunityHandler,
    CreateOpportunityHandler,
    GetHighScoreOpportunitiesHandler,
    GetOpportunityHandler,
    GetUrgentOpportunitiesHandler,
    ListOpportunitiesHandler,
    RejectOpportunityHandler,
    ScoreOpportunityHandler,
)
from app.cqrs.queries import (
    GetContactQuery,
    GetDraftQuery,
    GetHighScoreOpportunitiesQuery,
    GetOpportunityQuery,
    GetSubmissionQuery,
    GetUrgentOpportunitiesQuery,
    ListContactsQuery,
    ListDraftsQuery,
    ListOpportunitiesQuery,
    ListSubmissionsQuery,
)
from app.cqrs.submission_handlers import (
    CreateSubmissionHandler,
    GetSubmissionHandler,
    ListSubmissionsHandler,
    MarkSubmissionLostHandler,
    MarkSubmissionWonHandler,
)

logger = logging.getLogger(__name__)


def setup_cqrs():
    """Register all CQRS handlers."""
    
    # Opportunity Command Handlers
    mediator.register_command_handler(
        CreateOpportunityCommand,
        CreateOpportunityHandler()
    )
    mediator.register_command_handler(
        ScoreOpportunityCommand,
        ScoreOpportunityHandler()
    )
    mediator.register_command_handler(
        ApproveOpportunityCommand,
        ApproveOpportunityHandler()
    )
    mediator.register_command_handler(
        RejectOpportunityCommand,
        RejectOpportunityHandler()
    )
    
    # Opportunity Query Handlers
    mediator.register_query_handler(
        GetOpportunityQuery,
        GetOpportunityHandler()
    )
    mediator.register_query_handler(
        ListOpportunitiesQuery,
        ListOpportunitiesHandler()
    )
    mediator.register_query_handler(
        GetHighScoreOpportunitiesQuery,
        GetHighScoreOpportunitiesHandler()
    )
    mediator.register_query_handler(
        GetUrgentOpportunitiesQuery,
        GetUrgentOpportunitiesHandler()
    )
    
    # Submission Command Handlers
    mediator.register_command_handler(
        CreateSubmissionCommand,
        CreateSubmissionHandler()
    )
    mediator.register_command_handler(
        MarkSubmissionWonCommand,
        MarkSubmissionWonHandler()
    )
    mediator.register_command_handler(
        MarkSubmissionLostCommand,
        MarkSubmissionLostHandler()
    )
    
    # Submission Query Handlers
    mediator.register_query_handler(
        GetSubmissionQuery,
        GetSubmissionHandler()
    )
    mediator.register_query_handler(
        ListSubmissionsQuery,
        ListSubmissionsHandler()
    )
    
    # Contact Command Handlers
    mediator.register_command_handler(
        CreateContactCommand,
        CreateContactHandler()
    )
    
    # Contact Query Handlers
    mediator.register_query_handler(
        GetContactQuery,
        GetContactHandler()
    )
    mediator.register_query_handler(
        ListContactsQuery,
        ListContactsHandler()
    )
    
    # Draft Command Handlers
    mediator.register_command_handler(
        ApproveDraftCommand,
        ApproveDraftHandler()
    )
    mediator.register_command_handler(
        RejectDraftCommand,
        RejectDraftHandler()
    )
    
    # Draft Query Handlers
    mediator.register_query_handler(
        GetDraftQuery,
        GetDraftHandler()
    )
    mediator.register_query_handler(
        ListDraftsQuery,
        ListDraftsHandler()
    )
    
    logger.info("CQRS handlers registered successfully")
