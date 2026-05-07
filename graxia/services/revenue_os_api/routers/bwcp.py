"""
BWCP Message API Routes
CEO dashboard endpoints for agent communication visibility
"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db_session
from ....packages.revenue_os.models import BWCPMessage
from ....packages.revenue_os.enums import AgentType, BWCPMessageType
from ....packages.revenue_os.schemas.bwcp_schemas import (
    BWCPMessageResponse,
    BWCPMessageList,
    BWCPConversationResponse,
    BWCPUnreadCount,
)
from ..dependencies import require_admin_api_key

router = APIRouter(prefix="/bwcp", tags=["BWCP Messages"])


@router.get(
    "/inbox/{recipient_agent}",
    response_model=BWCPMessageList,
    summary="Get BWCP inbox for agent",
    description="Retrieve pending (undelivered) messages for a specific agent",
)
async def get_agent_inbox(
    recipient_agent: AgentType,
    delivered: Optional[bool] = Query(False, description="Filter by delivery status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Get inbox messages for specified agent."""
    query = (
        select(BWCPMessage)
        .where(
            and_(
                BWCPMessage.recipient_agent == recipient_agent,
                BWCPMessage.delivered == delivered,
            )
        )
        .order_by(desc(BWCPMessage.created_at))
        .offset(offset)
        .limit(limit)
    )
    
    result = await db.execute(query)
    messages = result.scalars().all()
    
    # Get total count
    count_result = await db.execute(
        select(BWCPMessage)
        .where(
            and_(
                BWCPMessage.recipient_agent == recipient_agent,
                BWCPMessage.delivered == delivered,
            )
        )
    )
    total = len(count_result.scalars().all())
    
    return {
        "items": messages,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/conversation/{conversation_id}",
    response_model=BWCPConversationResponse,
    summary="Get BWCP conversation thread",
    description="Retrieve all messages in a conversation thread",
)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Get all messages in a conversation thread."""
    result = await db.execute(
        select(BWCPMessage)
        .where(BWCPMessage.conversation_id == conversation_id)
        .order_by(asc(BWCPMessage.created_at))
    )
    messages = result.scalars().all()
    
    if not messages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )
    
    return {
        "conversation_id": conversation_id,
        "messages": messages,
        "message_count": len(messages),
        "participants": list(set(
            [m.sender_agent.value for m in messages] +
            [m.recipient_agent.value for m in messages]
        )),
        "started_at": messages[0].created_at if messages else None,
        "last_message_at": messages[-1].created_at if messages else None,
    }


@router.post(
    "/messages/{message_id}/delivered",
    response_model=BWCPMessageResponse,
    summary="Mark message as delivered",
)
async def mark_message_delivered(
    message_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Mark a BWCP message as delivered."""
    from ....packages.revenue_os.services import BWCPService
    
    success = await BWCPService.mark_delivered(db, message_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message {message_id} not found",
        )
    
    # Fetch updated message
    result = await db.execute(
        select(BWCPMessage).where(BWCPMessage.id == message_id)
    )
    message = result.scalar_one()
    
    return message


@router.post(
    "/messages/{message_id}/read",
    response_model=BWCPMessageResponse,
    summary="Mark message as read",
)
async def mark_message_read(
    message_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Mark a BWCP message as read."""
    from ....packages.revenue_os.services import BWCPService
    
    success = await BWCPService.mark_read(db, message_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message {message_id} not found",
        )
    
    result = await db.execute(
        select(BWCPMessage).where(BWCPMessage.id == message_id)
    )
    message = result.scalar_one()
    
    return message


@router.get(
    "/unread-count/{recipient_agent}",
    response_model=BWCPUnreadCount,
    summary="Get unread message count",
    description="Count undelivered messages for an agent",
)
async def get_unread_count(
    recipient_agent: AgentType,
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Get count of undelivered messages for agent."""
    result = await db.execute(
        select(BWCPMessage)
        .where(
            and_(
                BWCPMessage.recipient_agent == recipient_agent,
                BWCPMessage.delivered == False,
            )
        )
    )
    messages = result.scalars().all()
    
    # Count by message type
    by_type = {}
    for m in messages:
        by_type[m.message_type.value] = by_type.get(m.message_type.value, 0) + 1
    
    return {
        "recipient_agent": recipient_agent.value,
        "total_undelivered": len(messages),
        "by_type": by_type,
    }


@router.get(
    "/messages",
    response_model=BWCPMessageList,
    summary="List all BWCP messages",
    description="Query BWCP messages with filters",
)
async def list_messages(
    sender_agent: Optional[AgentType] = Query(None),
    recipient_agent: Optional[AgentType] = Query(None),
    message_type: Optional[BWCPMessageType] = Query(None),
    delivered: Optional[bool] = Query(None),
    campaign_id: Optional[UUID] = Query(None),
    lead_id: Optional[UUID] = Query(None),
    approval_id: Optional[UUID] = Query(None),
    incident_id: Optional[UUID] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Query BWCP messages with filters."""
    query = select(BWCPMessage)
    
    # Build filter conditions
    conditions = []
    if sender_agent:
        conditions.append(BWCPMessage.sender_agent == sender_agent)
    if recipient_agent:
        conditions.append(BWCPMessage.recipient_agent == recipient_agent)
    if message_type:
        conditions.append(BWCPMessage.message_type == message_type)
    if delivered is not None:
        conditions.append(BWCPMessage.delivered == delivered)
    if campaign_id:
        conditions.append(BWCPMessage.campaign_id == campaign_id)
    if lead_id:
        conditions.append(BWCPMessage.lead_id == lead_id)
    if approval_id:
        conditions.append(BWCPMessage.approval_id == approval_id)
    if incident_id:
        conditions.append(BWCPMessage.incident_id == incident_id)
    
    if conditions:
        query = query.where(and_(*conditions))
    
    # Get total count
    count_result = await db.execute(query)
    total = len(count_result.scalars().all())
    
    # Apply pagination
    query = query.order_by(desc(BWCPMessage.created_at)).offset(offset).limit(limit)
    result = await db.execute(query)
    messages = result.scalars().all()
    
    return {
        "items": messages,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/stats",
    summary="Get BWCP statistics",
    description="Message statistics by agent and type",
)
async def get_bwcp_stats(
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_api_key),
):
    """Get BWCP message statistics."""
    from sqlalchemy import func
    
    # Messages by sender
    sender_stats = await db.execute(
        select(BWCPMessage.sender_agent, func.count(BWCPMessage.id))
        .group_by(BWCPMessage.sender_agent)
    )
    
    # Messages by recipient
    recipient_stats = await db.execute(
        select(BWCPMessage.recipient_agent, func.count(BWCPMessage.id))
        .group_by(BWCPMessage.recipient_agent)
    )
    
    # Messages by type
    type_stats = await db.execute(
        select(BWCPMessage.message_type, func.count(BWCPMessage.id))
        .group_by(BWCPMessage.message_type)
    )
    
    # Undelivered count
    undelivered = await db.execute(
        select(func.count(BWCPMessage.id))
        .where(BWCPMessage.delivered == False)
    )
    
    return {
        "by_sender": {k.value: v for k, v in sender_stats.all()},
        "by_recipient": {k.value: v for k, v in recipient_stats.all()},
        "by_type": {k.value: v for k, v in type_stats.all()},
        "total_undelivered": undelivered.scalar() or 0,
    }
