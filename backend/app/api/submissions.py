"""
Submissions API - Refactored to use CQRS Pattern

This module demonstrates the integration of:
- CQRS (Command Query Responsibility Segregation)
- Repository Pattern
- Result Type for error handling
- Mediator Pattern
"""
import logging
from decimal import Decimal
from typing import Annotated, TypedDict
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.cqrs.handlers import mediator
from app.cqrs.commands import (
    CreateSubmissionCommand,
    MarkSubmissionWonCommand,
    MarkSubmissionLostCommand,
)
from app.cqrs.queries import ListSubmissionsQuery
from app.schemas.submission import SubmissionCreate, SubmissionOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/submissions", tags=["submissions"])

SubmissionStatus = Annotated[str | None, Query()]
ActualValueParam = Annotated[Decimal, Query()]
LostReasonParam = Annotated[str, Query()]


class StatusResponse(TypedDict):
    status: str


@router.get("", response_model=list[SubmissionOut])
async def list_submissions(
    status: SubmissionStatus = None,
) -> list[SubmissionOut]:
    """
    List submissions using CQRS Query.
    
    This endpoint demonstrates:
    - Using ListSubmissionsQuery instead of direct DB access
    - Using mediator.send_query() for query execution
    - Using Result type for error handling
    """
    try:
        # Create query
        query = ListSubmissionsQuery(status=status)
        
        # Send via mediator
        result = await mediator.send_query(query)
        
        # Handle result
        if result.is_err():
            logger.error(f"Query failed: {result.error}")
            return []
        
        # Unwrap and return
        submissions = result.unwrap()
        return [SubmissionOut.model_validate(sub) for sub in submissions]
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return []


@router.post("", response_model=SubmissionOut, status_code=201)
async def create_submission(data: SubmissionCreate) -> SubmissionOut:
    """
    Create submission using CQRS Command.
    
    This endpoint demonstrates:
    - Using CreateSubmissionCommand instead of direct DB insert
    - Using mediator.send_command() for command execution
    - Using Result type for error handling
    """
    # Create command
    command = CreateSubmissionCommand(
        opportunity_id=data.opportunity_id,
        contact_id=data.contact_id,
        type=data.type,
        title=data.title,
        content=data.content,
        subject_line=data.subject_line,
        proposed_value=data.proposed_value,
        currency=data.currency,
    )
    
    # Send via mediator
    result = await mediator.send_command(command)
    
    # Handle result
    if result.is_err():
        logger.error(f"Command failed: {result.error}")
        raise HTTPException(status_code=400, detail=str(result.error))
    
    # Unwrap and return
    submission = result.unwrap()
    return SubmissionOut.model_validate(submission)


@router.patch("/{sub_id}/mark-won")
async def mark_won(
    sub_id: UUID,
    actual_value: ActualValueParam = Decimal("0"),
) -> StatusResponse:
    """
    Mark submission as won using CQRS Command.
    
    This endpoint demonstrates:
    - Using MarkSubmissionWonCommand instead of direct DB update
    - Using mediator.send_command() for command execution
    - Using Result type for error handling
    """
    # Create command
    command = MarkSubmissionWonCommand(
        submission_id=sub_id,
        actual_value=float(actual_value)
    )
    
    # Send via mediator
    result = await mediator.send_command(command)
    
    # Handle result
    if result.is_err():
        logger.error(f"Command failed: {result.error}")
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # Unwrap and return
    submission = result.unwrap()
    return {"status": submission.status}


@router.patch("/{sub_id}/mark-lost")
async def mark_lost(
    sub_id: UUID,
    lost_reason: LostReasonParam = "unknown",
) -> StatusResponse:
    """
    Mark submission as lost using CQRS Command.
    
    This endpoint demonstrates:
    - Using MarkSubmissionLostCommand instead of direct DB update
    - Using mediator.send_command() for command execution
    - Using Result type for error handling
    """
    # Create command
    command = MarkSubmissionLostCommand(
        submission_id=sub_id,
        lost_reason=lost_reason
    )
    
    # Send via mediator
    result = await mediator.send_command(command)
    
    # Handle result
    if result.is_err():
        logger.error(f"Command failed: {result.error}")
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # Unwrap and return
    submission = result.unwrap()
    return {"status": submission.status}
