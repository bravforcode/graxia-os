"""
Revenue OS BWCP Service
Belief-Will-Can-Plan message service for agent choreography

Implements BWCP pattern for agent communication:
- Belief: What the agent believes about the situation
- Will: What the agent intends to do
- Can: What the agent is capable of
- Plan: How the agent will execute
"""
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4
from datetime import datetime
import structlog

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import BWCPMessage, OutboxEvent
from ..enums import AgentType, BWCPMessageType

logger = structlog.get_logger()


class BWCPService:
    """
    BWCP Message Service
    
    Manages agent-to-agent communication using BWCP pattern.
    Messages are persisted to database for audit and replay.
    """

    @staticmethod
    async def send_message(
        db: AsyncSession,
        sender_agent: AgentType,
        recipient_agent: AgentType,
        message_type: BWCPMessageType,
        conversation_id: str,
        belief: str,
        will: str,
        can: Optional[Dict[str, Any]] = None,
        plan: Optional[Dict[str, Any]] = None,
        campaign_id: Optional[UUID] = None,
        lead_id: Optional[UUID] = None,
        approval_id: Optional[UUID] = None,
        incident_id: Optional[UUID] = None,
    ) -> BWCPMessage:
        """
        Send BWCP message from one agent to another.
        
        Args:
            db: Database session
            sender_agent: Agent sending the message
            recipient_agent: Agent receiving the message
            message_type: Type of BWCP message
            conversation_id: Conversation thread ID
            belief: Agent's belief about the situation
            will: Agent's intended action
            can: Agent's capabilities (JSON)
            plan: Agent's execution plan (JSON)
            campaign_id: Optional related campaign
            lead_id: Optional related lead
            approval_id: Optional related approval
            incident_id: Optional related incident
        
        Returns:
            BWCPMessage: Created message
        """
        message = BWCPMessage(
            conversation_id=conversation_id,
            sender_agent=sender_agent,
            recipient_agent=recipient_agent,
            message_type=message_type,
            belief=belief,
            will=will,
            can=can or {},
            plan=plan or {},
            campaign_id=campaign_id,
            lead_id=lead_id,
            approval_id=approval_id,
            incident_id=incident_id,
            delivered=False,
        )
        db.add(message)
        await db.flush()
        
        logger.info(
            "bwcp_message_sent",
            message_id=str(message.id),
            sender=sender_agent.value,
            recipient=recipient_agent.value,
            message_type=message_type.value,
            conversation_id=conversation_id,
        )
        
        return message

    @staticmethod
    async def get_pending_messages(
        db: AsyncSession,
        recipient_agent: AgentType,
        limit: int = 50,
    ) -> List[BWCPMessage]:
        """
        Get undelivered messages for an agent.
        
        Args:
            db: Database session
            recipient_agent: Agent to get messages for
            limit: Maximum messages to return
        
        Returns:
            List[BWCPMessage]: Pending messages
        """
        result = await db.execute(
            select(BWCPMessage)
            .where(
                and_(
                    BWCPMessage.recipient_agent == recipient_agent,
                    BWCPMessage.delivered == False,
                )
            )
            .order_by(desc(BWCPMessage.created_at))
            .limit(limit)
        )
        
        return result.scalars().all()

    @staticmethod
    async def mark_delivered(
        db: AsyncSession,
        message_id: UUID,
    ) -> bool:
        """
        Mark message as delivered.
        
        Args:
            db: Database session
            message_id: Message UUID
        
        Returns:
            bool: True if marked delivered
        """
        result = await db.execute(
            select(BWCPMessage).where(BWCPMessage.id == message_id)
        )
        message = result.scalar_one_or_none()
        
        if not message:
            return False
        
        message.delivered = True
        message.delivered_at = datetime.utcnow()
        await db.flush()
        
        logger.debug(
            "bwcp_message_delivered",
            message_id=str(message_id),
        )
        
        return True

    @staticmethod
    async def mark_read(
        db: AsyncSession,
        message_id: UUID,
    ) -> bool:
        """
        Mark message as read.
        
        Args:
            db: Database session
            message_id: Message UUID
        
        Returns:
            bool: True if marked read
        """
        result = await db.execute(
            select(BWCPMessage).where(BWCPMessage.id == message_id)
        )
        message = result.scalar_one_or_none()
        
        if not message:
            return False
        
        message.read_at = datetime.utcnow()
        await db.flush()
        
        return True

    @staticmethod
    async def get_conversation_history(
        db: AsyncSession,
        conversation_id: str,
        limit: int = 100,
    ) -> List[BWCPMessage]:
        """
        Get all messages in a conversation.
        
        Args:
            db: Database session
            conversation_id: Conversation thread ID
            limit: Maximum messages to return
        
        Returns:
            List[BWCPMessage]: Conversation messages
        """
        result = await db.execute(
            select(BWCPMessage)
            .where(BWCPMessage.conversation_id == conversation_id)
            .order_by(desc(BWCPMessage.created_at))
            .limit(limit)
        )
        
        return result.scalars().all()

    @staticmethod
    async def create_campaign_created_message(
        db: AsyncSession,
        conversation_id: str,
        campaign_id: UUID,
        campaign_name: str,
        sender_agent: AgentType,
        recipient_agent: AgentType,
    ) -> BWCPMessage:
        """Create campaign created BWCP message."""
        return await BWCPService.send_message(
            db=db,
            sender_agent=sender_agent,
            recipient_agent=recipient_agent,
            message_type=BWCPMessageType.CAMPAIGN_CREATED,
            conversation_id=conversation_id,
            belief=f"New campaign '{campaign_name}' has been created and requires review.",
            will="Monitor campaign performance and escalate if budget issues arise.",
            can={"actions": ["monitor", "alert", "escalate"]},
            plan={
                "step_1": "Review campaign parameters",
                "step_2": "Set up monitoring alerts",
                "step_3": "Report to CEO on performance",
            },
            campaign_id=campaign_id,
        )

    @staticmethod
    async def create_lead_identified_message(
        db: AsyncSession,
        conversation_id: str,
        lead_id: UUID,
        email: str,
        score: int,
        sender_agent: AgentType,
        recipient_agent: AgentType,
    ) -> BWCPMessage:
        """Create lead identified BWCP message."""
        return await BWCPService.send_message(
            db=db,
            sender_agent=sender_agent,
            recipient_agent=recipient_agent,
            message_type=BWCPMessageType.LEAD_IDENTIFIED,
            conversation_id=conversation_id,
            belief=f"High-value lead identified: {email} with score {score}/100.",
            will="Nurture lead through sales funnel.",
            can={"actions": ["email", "score", "track"]},
            plan={
                "step_1": "Send welcome email",
                "step_2": "Schedule follow-up sequence",
                "step_3": "Monitor engagement",
            },
            lead_id=lead_id,
        )

    @staticmethod
    async def create_approval_required_message(
        db: AsyncSession,
        conversation_id: str,
        approval_id: UUID,
        approval_type: str,
        requested_by: str,
        sender_agent: AgentType,
        recipient_agent: AgentType = AgentType.CHIEF_OF_STAFF,
    ) -> BWCPMessage:
        """Create approval required BWCP message."""
        return await BWCPService.send_message(
            db=db,
            sender_agent=sender_agent,
            recipient_agent=recipient_agent,
            message_type=BWCPMessageType.APPROVAL_REQUIRED,
            conversation_id=conversation_id,
            belief=f"{approval_type} requires CEO approval. Requested by {requested_by}.",
            will="Secure CEO approval before proceeding.",
            can={"actions": ["request_approval", "escalate", "notify"]},
            plan={
                "step_1": "Present approval request to CEO",
                "step_2": "Wait for CEO decision",
                "step_3": "Execute approved action or notify rejection",
            },
            approval_id=approval_id,
        )

    @staticmethod
    async def create_incident_created_message(
        db: AsyncSession,
        conversation_id: str,
        incident_id: UUID,
        severity: str,
        title: str,
        sender_agent: AgentType,
        recipient_agent: AgentType = AgentType.CHIEF_OF_STAFF,
    ) -> BWCPMessage:
        """Create incident created BWCP message."""
        return await BWCPService.send_message(
            db=db,
            sender_agent=sender_agent,
            recipient_agent=recipient_agent,
            message_type=BWCPMessageType.INCIDENT_CREATED,
            conversation_id=conversation_id,
            belief=f"{severity} incident: {title}. Immediate attention required.",
            will="Coordinate incident response and notify stakeholders.",
            can={"actions": ["alert", "escalate", "coordinate", "resolve"]},
            plan={
                "step_1": "Assess incident impact",
                "step_2": "Alert relevant teams",
                "step_3": "Coordinate resolution",
                "step_4": "Document and close",
            },
            incident_id=incident_id,
        )

    @staticmethod
    async def create_order_fulfilled_message(
        db: AsyncSession,
        conversation_id: str,
        order_id: UUID,
        customer_email: str,
        product_name: str,
        sender_agent: AgentType,
        recipient_agent: AgentType = AgentType.SALES,
    ) -> BWCPMessage:
        """Create order fulfilled BWCP message."""
        return await BWCPService.send_message(
            db=db,
            sender_agent=sender_agent,
            recipient_agent=recipient_agent,
            message_type=BWCPMessageType.ORDER_FULFILLED,
            conversation_id=conversation_id,
            belief=f"Order fulfilled for {customer_email}. Product: {product_name}.",
            will="Update customer record and trigger follow-up sequence.",
            can={"actions": ["update_crm", "trigger_followup", "notify_sales"]},
            plan={
                "step_1": "Update customer status to active",
                "step_2": "Send satisfaction survey",
                "step_3": "Add to nurture campaign",
            },
        )


class BWCPConversationManager:
    """
    Manager for BWCP conversations.
    
    Creates unique conversation IDs and tracks conversation state.
    """
    
    @staticmethod
    def generate_conversation_id(prefix: str = "conv") -> str:
        """Generate unique conversation ID."""
        return f"{prefix}:{uuid4().hex[:12]}:{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    @staticmethod
    def generate_correlation_id() -> str:
        """Generate unique correlation ID for distributed tracing."""
        return f"corr-{uuid4().hex[:16]}"
