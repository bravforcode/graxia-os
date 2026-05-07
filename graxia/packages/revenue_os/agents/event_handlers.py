"""
Revenue OS Agent Event Handlers
Consume Redis Stream events and produce BWCP messages

Agents:
- VisionaryAgent: Consumes campaign, incident events
- SalesAgent: Consumes lead, order events  
- ChiefOfStaffAgent: Consumes approval, incident, refund events
"""
from typing import Dict, Any, Optional
from datetime import datetime
import structlog
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.redis_streams import RedisStreamClient
from ..services.bwcp_service import BWCPService, BWCPConversationManager
from ..db import get_db_session
from ..enums import (
    AgentType, BWCPMessageType, LeadStatus, 
    CampaignStatus, IncidentSeverity
)

logger = structlog.get_logger()


class BaseAgentHandler:
    """Base class for agent event handlers."""
    
    agent_type: AgentType
    interested_events: list[str] = []
    
    def __init__(self, redis_client: Optional[RedisStreamClient] = None):
        self.redis = redis_client
        self.conversation_manager = BWCPConversationManager()
    
    async def handle_event(self, event: Dict[str, Any]) -> bool:
        """
        Process an event. Override in subclasses.
        
        Args:
            event: Event dict from Redis Stream
        
        Returns:
            bool: True if handled successfully
        """
        event_type = event.get("event_type", "")
        
        if event_type not in self.interested_events:
            return False
        
        # Get database session
        async with get_db_session() as db:
            try:
                return await self._process_event(db, event)
            except Exception as e:
                logger.error(
                    f"{self.agent_type.value}_event_processing_failed",
                    event_type=event_type,
                    error=str(e),
                )
                return False
    
    async def _process_event(self, db: AsyncSession, event: Dict[str, Any]) -> bool:
        """Override in subclasses to implement event processing."""
        raise NotImplementedError
    
    def _get_correlation_id(self, event: Dict[str, Any]) -> str:
        """Get or generate correlation ID for event."""
        return event.get("correlation_id") or self.conversation_manager.generate_correlation_id()


class VisionaryAgentHandler(BaseAgentHandler):
    """
    Visionary Agent Event Handler
    
    Responsibilities:
    - Monitor campaign performance and target achievement
    - Track incidents that affect strategic direction
    - Alert on critical business events
    
    Consumes: campaign_created, campaign_target_hit, incident_created
    """
    
    agent_type = AgentType.VISIONARY
    interested_events = [
        "campaign_created",
        "campaign_target_hit", 
        "campaign_paused",
        "incident_created",
    ]
    
    async def _process_event(self, db: AsyncSession, event: Dict[str, Any]) -> bool:
        """Process Visionary Agent events."""
        event_type = event.get("event_type", "")
        payload = event.get("payload", {})
        correlation_id = self._get_correlation_id(event)
        
        if event_type == "campaign_created":
            return await self._handle_campaign_created(db, payload, correlation_id)
        
        elif event_type == "campaign_target_hit":
            return await self._handle_campaign_target_hit(db, payload, correlation_id)
        
        elif event_type == "campaign_paused":
            return await self._handle_campaign_paused(db, payload, correlation_id)
        
        elif event_type == "incident_created":
            return await self._handle_incident_created(db, payload, correlation_id)
        
        return False
    
    async def _handle_campaign_created(
        self, db: AsyncSession, payload: Dict, correlation_id: str
    ) -> bool:
        """Handle new campaign creation."""
        campaign_id = payload.get("campaign_id")
        campaign_name = payload.get("campaign_name", "Unknown")
        
        conversation_id = self.conversation_manager.generate_conversation_id("visionary")
        
        await BWCPService.send_message(
            db=db,
            sender_agent=AgentType.VISIONARY,
            recipient_agent=AgentType.CHIEF_OF_STAFF,
            message_type=BWCPMessageType.CAMPAIGN_CREATED,
            conversation_id=conversation_id,
            belief=f"New campaign '{campaign_name}' launched. Monitoring for performance.",
            will="Track campaign progress and report milestones to CEO.",
            can={"actions": ["monitor", "analyze", "report"]},
            plan={
                "step_1": "Review campaign objectives",
                "step_2": "Set performance benchmarks",
                "step_3": "Weekly progress reports",
            },
            campaign_id=campaign_id,
        )
        
        logger.info(
            "visionary_campaign_created",
            campaign_id=campaign_id,
            campaign_name=campaign_name,
            correlation_id=correlation_id,
        )
        
        return True
    
    async def _handle_campaign_target_hit(
        self, db: AsyncSession, payload: Dict, correlation_id: str
    ) -> bool:
        """Handle campaign target achievement."""
        campaign_id = payload.get("campaign_id")
        campaign_name = payload.get("campaign_name", "Unknown")
        target_revenue = payload.get("target_revenue_cents", 0) / 100
        actual_revenue = payload.get("actual_revenue_cents", 0) / 100
        
        conversation_id = self.conversation_manager.generate_conversation_id("visionary")
        
        await BWCPService.send_message(
            db=db,
            sender_agent=AgentType.VISIONARY,
            recipient_agent=AgentType.CHIEF_OF_STAFF,
            message_type=BWCPMessageType.CAMPAIGN_TARGET_HIT,
            conversation_id=conversation_id,
            belief=f"Campaign '{campaign_name}' exceeded target! Actual: ${actual_revenue:.2f}, Target: ${target_revenue:.2f}",
            will="Analyze success factors and recommend campaign expansion.",
            can={"actions": ["analyze", "recommend", "escalate"]},
            plan={
                "step_1": "Document success factors",
                "step_2": "Recommend budget increase",
                "step_3": "Present to CEO for decision",
            },
            campaign_id=campaign_id,
        )
        
        logger.info(
            "visionary_campaign_target_hit",
            campaign_id=campaign_id,
            target_revenue=target_revenue,
            actual_revenue=actual_revenue,
        )
        
        return True
    
    async def _handle_campaign_paused(
        self, db: AsyncSession, payload: Dict, correlation_id: str
    ) -> bool:
        """Handle campaign pause (budget or incident)."""
        campaign_id = payload.get("campaign_id")
        reason = payload.get("reason", "unknown")
        
        conversation_id = self.conversation_manager.generate_conversation_id("visionary")
        
        await BWCPService.send_message(
            db=db,
            sender_agent=AgentType.VISIONARY,
            recipient_agent=AgentType.CHIEF_OF_STAFF,
            message_type=BWCPMessageType.CAMPAIGN_PAUSED,
            conversation_id=conversation_id,
            belief=f"Campaign paused due to {reason}. Strategic review needed.",
            will="Assess impact on overall revenue strategy.",
            can={"actions": ["assess", "recommend", "escalate"]},
            plan={
                "step_1": "Evaluate pause impact",
                "step_2": "Review alternatives",
                "step_3": "Present options to CEO",
            },
            campaign_id=campaign_id,
        )
        
        return True
    
    async def _handle_incident_created(
        self, db: AsyncSession, payload: Dict, correlation_id: str
    ) -> bool:
        """Handle critical/high incidents."""
        severity = payload.get("severity", "low")
        
        # Only Visionary cares about HIGH and CRITICAL
        if severity not in ["high", "critical"]:
            return False
        
        incident_id = payload.get("incident_id")
        title = payload.get("title", "Unknown")
        
        conversation_id = self.conversation_manager.generate_conversation_id("visionary")
        
        await BWCPService.create_incident_created_message(
            db=db,
            conversation_id=conversation_id,
            incident_id=incident_id,
            severity=severity,
            title=title,
            sender_agent=AgentType.VISIONARY,
            recipient_agent=AgentType.CHIEF_OF_STAFF,
        )
        
        logger.warning(
            "visionary_critical_incident",
            incident_id=incident_id,
            severity=severity,
            title=title,
        )
        
        return True


class SalesAgentHandler(BaseAgentHandler):
    """
    Sales Agent Event Handler
    
    Responsibilities:
    - Track new leads and conversions
    - Monitor order fulfillment
    - Nurture leads through funnel
    
    Consumes: lead_identified, lead_converted, order_created, order_fulfilled
    """
    
    agent_type = AgentType.SALES
    interested_events = [
        "lead_identified",
        "lead_converted",
        "order_created",
        "order_fulfilled",
    ]
    
    async def _process_event(self, db: AsyncSession, event: Dict[str, Any]) -> bool:
        """Process Sales Agent events."""
        event_type = event.get("event_type", "")
        payload = event.get("payload", {})
        correlation_id = self._get_correlation_id(event)
        
        if event_type == "lead_identified":
            return await self._handle_lead_identified(db, payload, correlation_id)
        
        elif event_type == "lead_converted":
            return await self._handle_lead_converted(db, payload, correlation_id)
        
        elif event_type == "order_created":
            return await self._handle_order_created(db, payload, correlation_id)
        
        elif event_type == "order_fulfilled":
            return await self._handle_order_fulfilled(db, payload, correlation_id)
        
        return False
    
    async def _handle_lead_identified(
        self, db: AsyncSession, payload: Dict, correlation_id: str
    ) -> bool:
        """Handle new lead identification."""
        lead_id = payload.get("lead_id")
        email = payload.get("email", "unknown")
        score = payload.get("score", 0)
        source = payload.get("source", "unknown")
        
        conversation_id = self.conversation_manager.generate_conversation_id("sales")
        
        await BWCPService.create_lead_identified_message(
            db=db,
            conversation_id=conversation_id,
            lead_id=lead_id,
            email=email,
            score=score,
            sender_agent=AgentType.SALES,
            recipient_agent=AgentType.SALES,  # Self-assigned for tracking
        )
        
        logger.info(
            "sales_lead_identified",
            lead_id=lead_id,
            email=email,
            score=score,
            source=source,
        )
        
        return True
    
    async def _handle_lead_converted(
        self, db: AsyncSession, payload: Dict, correlation_id: str
    ) -> bool:
        """Handle lead-to-customer conversion."""
        lead_id = payload.get("lead_id")
        order_id = payload.get("order_id")
        customer_email = payload.get("customer_email", "unknown")
        amount = payload.get("amount_cents", 0) / 100
        
        conversation_id = self.conversation_manager.generate_conversation_id("sales")
        
        await BWCPService.send_message(
            db=db,
            sender_agent=AgentType.SALES,
            recipient_agent=AgentType.VISIONARY,
            message_type=BWCPMessageType.LEAD_CONVERTED,
            conversation_id=conversation_id,
            belief=f"Lead converted to customer! {customer_email} purchased ${amount:.2f}",
            will="Update metrics and request testimonial.",
            can={"actions": ["update_metrics", "request_testimonial", "upsell"]},
            plan={
                "step_1": "Update conversion metrics",
                "step_2": "Send thank you email",
                "step_3": "Request testimonial",
            },
            lead_id=lead_id,
        )
        
        logger.info(
            "sales_lead_converted",
            lead_id=lead_id,
            order_id=order_id,
            amount=amount,
        )
        
        return True
    
    async def _handle_order_created(
        self, db: AsyncSession, payload: Dict, correlation_id: str
    ) -> bool:
        """Handle new order creation."""
        order_id = payload.get("order_id")
        customer_email = payload.get("customer_email", "unknown")
        amount = payload.get("amount_cents", 0) / 100
        platform = payload.get("platform", "unknown")
        
        logger.info(
            "sales_order_created",
            order_id=order_id,
            customer=customer_email,
            amount=amount,
            platform=platform,
        )
        
        # Sales tracks but doesn't create BWCP message for order_created
        # FulfillmentService will handle that
        return True
    
    async def _handle_order_fulfilled(
        self, db: AsyncSession, payload: Dict, correlation_id: str
    ) -> bool:
        """Handle order fulfillment completion."""
        order_id = payload.get("order_id")
        customer_email = payload.get("customer_email", "unknown")
        product_name = payload.get("product_name", "Unknown")
        
        conversation_id = self.conversation_manager.generate_conversation_id("sales")
        
        await BWCPService.create_order_fulfilled_message(
            db=db,
            conversation_id=conversation_id,
            order_id=order_id,
            customer_email=customer_email,
            product_name=product_name,
            sender_agent=AgentType.SALES,
            recipient_agent=AgentType.SALES,
        )
        
        logger.info(
            "sales_order_fulfilled",
            order_id=order_id,
            customer=customer_email,
            product=product_name,
        )
        
        return True


class ChiefOfStaffHandler(BaseAgentHandler):
    """
    Chief of Staff Agent Event Handler
    
    Responsibilities:
    - Handle approval requests (HR-01, HR-02 compliance)
    - Escalate critical incidents (HR-14 compliance)
    - Monitor refunds and financial mutations (HR-10 compliance)
    
    Consumes: approval_required, approval_approved, approval_rejected,
              incident_created, order_refunded
    """
    
    agent_type = AgentType.CHIEF_OF_STAFF
    interested_events = [
        "approval_required",
        "approval_approved",
        "approval_rejected",
        "incident_created",
        "order_refunded",
    ]
    
    async def _process_event(self, db: AsyncSession, event: Dict[str, Any]) -> bool:
        """Process Chief of Staff events."""
        event_type = event.get("event_type", "")
        payload = event.get("payload", {})
        correlation_id = self._get_correlation_id(event)
        
        if event_type == "approval_required":
            return await self._handle_approval_required(db, payload, correlation_id)
        
        elif event_type == "approval_approved":
            return await self._handle_approval_approved(db, payload, correlation_id)
        
        elif event_type == "approval_rejected":
            return await self._handle_approval_rejected(db, payload, correlation_id)
        
        elif event_type == "incident_created":
            return await self._handle_incident_created(db, payload, correlation_id)
        
        elif event_type == "order_refunded":
            return await self._handle_order_refunded(db, payload, correlation_id)
        
        return False
    
    async def _handle_approval_required(
        self, db: AsyncSession, payload: Dict, correlation_id: str
    ) -> bool:
        """Handle approval request (HR-01, HR-02)."""
        approval_id = payload.get("approval_id")
        approval_type = payload.get("approval_type", "unknown")
        requested_by = payload.get("requested_by", "unknown")
        priority = payload.get("priority", "normal")
        
        conversation_id = self.conversation_manager.generate_conversation_id("cos")
        
        await BWCPService.create_approval_required_message(
            db=db,
            conversation_id=conversation_id,
            approval_id=approval_id,
            approval_type=approval_type,
            requested_by=requested_by,
            sender_agent=AgentType.CHIEF_OF_STAFF,
            recipient_agent=AgentType.CHIEF_OF_STAFF,  # Self for tracking
        )
        
        # CRITICAL: Notify CEO immediately for high priority
        if priority == "high":
            await BWCPService.send_message(
                db=db,
                sender_agent=AgentType.CHIEF_OF_STAFF,
                recipient_agent=AgentType.VISIONARY,  # CEO proxy
                message_type=BWCPMessageType.APPROVAL_REQUIRED,
                conversation_id=conversation_id,
                belief=f"URGENT: {approval_type} requires immediate CEO approval.",
                will="Escalate to CEO for immediate decision.",
                can={"actions": ["escalate", "notify", "track"]},
                plan={
                    "step_1": "Alert CEO immediately",
                    "step_2": "Track CEO response",
                    "step_3": "Execute decision",
                },
                approval_id=approval_id,
            )
        
        logger.info(
            "cos_approval_required",
            approval_id=approval_id,
            approval_type=approval_type,
            priority=priority,
        )
        
        return True
    
    async def _handle_approval_approved(
        self, db: AsyncSession, payload: Dict, correlation_id: str
    ) -> bool:
        """Handle approval granted."""
        approval_id = payload.get("approval_id")
        approver = payload.get("approver", "CEO")
        
        conversation_id = self.conversation_manager.generate_conversation_id("cos")
        
        await BWCPService.send_message(
            db=db,
            sender_agent=AgentType.CHIEF_OF_STAFF,
            recipient_agent=AgentType.SALES,
            message_type=BWCPMessageType.APPROVAL_APPROVED,
            conversation_id=conversation_id,
            belief=f"Approval {approval_id} granted by {approver}. Proceeding with execution.",
            will="Execute approved action and confirm completion.",
            can={"actions": ["execute", "confirm", "notify"]},
            plan={
                "step_1": "Execute approved action",
                "step_2": "Confirm completion",
                "step_3": "Notify stakeholders",
            },
            approval_id=approval_id,
        )
        
        logger.info(
            "cos_approval_approved",
            approval_id=approval_id,
            approver=approver,
        )
        
        return True
    
    async def _handle_approval_rejected(
        self, db: AsyncSession, payload: Dict, correlation_id: str
    ) -> bool:
        """Handle approval rejected."""
        approval_id = payload.get("approval_id")
        reason = payload.get("reason", "No reason provided")
        
        conversation_id = self.conversation_manager.generate_conversation_id("cos")
        
        await BWCPService.send_message(
            db=db,
            sender_agent=AgentType.CHIEF_OF_STAFF,
            recipient_agent=AgentType.SALES,
            message_type=BWCPMessageType.APPROVAL_REJECTED,
            conversation_id=conversation_id,
            belief=f"Approval {approval_id} rejected. Reason: {reason}",
            will="Notify requester and document rejection.",
            can={"actions": ["notify", "document", "archive"]},
            plan={
                "step_1": "Notify requester",
                "step_2": "Document rejection reason",
                "step_3": "Archive request",
            },
            approval_id=approval_id,
        )
        
        return True
    
    async def _handle_incident_created(
        self, db: AsyncSession, payload: Dict, correlation_id: str
    ) -> bool:
        """Handle incident escalation (HR-14)."""
        incident_id = payload.get("incident_id")
        severity = payload.get("severity", "low")
        title = payload.get("title", "Unknown")
        
        # ChiefOfStaff handles ALL incidents (not just high/critical)
        conversation_id = self.conversation_manager.generate_conversation_id("cos")
        
        await BWCPService.create_incident_created_message(
            db=db,
            conversation_id=conversation_id,
            incident_id=incident_id,
            severity=severity,
            title=title,
            sender_agent=AgentType.CHIEF_OF_STAFF,
            recipient_agent=AgentType.CHIEF_OF_STAFF,
        )
        
        # HR-14: Escalate to ChiefOfStaff immediately for critical
        if severity == "critical":
            await BWCPService.send_message(
                db=db,
                sender_agent=AgentType.CHIEF_OF_STAFF,
                recipient_agent=AgentType.VISIONARY,
                message_type=BWCPMessageType.INCIDENT_CREATED,
                conversation_id=conversation_id,
                belief=f"CRITICAL INCIDENT: {title}. Immediate CEO attention required.",
                will="Coordinate emergency response and brief CEO.",
                can={"actions": ["escalate", "coordinate", "brief", "resolve"]},
                plan={
                    "step_1": "Alert CEO immediately",
                    "step_2": "Coordinate response team",
                    "step_3": "Provide status updates every 15 min",
                },
                incident_id=incident_id,
            )
            
            logger.error(
                "cos_critical_incident_escalated",
                incident_id=incident_id,
                title=title,
            )
        
        return True
    
    async def _handle_order_refunded(
        self, db: AsyncSession, payload: Dict, correlation_id: str
    ) -> bool:
        """Handle refund notification (HR-16)."""
        order_id = payload.get("order_id")
        refund_id = payload.get("refund_id")
        amount = payload.get("amount_cents", 0) / 100
        reason = payload.get("reason", "unknown")
        
        conversation_id = self.conversation_manager.generate_conversation_id("cos")
        
        await BWCPService.send_message(
            db=db,
            sender_agent=AgentType.CHIEF_OF_STAFF,
            recipient_agent=AgentType.VISIONARY,
            message_type=BWCPMessageType.ORDER_REFUNDED,
            conversation_id=conversation_id,
            belief=f"Refund processed: ${amount:.2f} for order {order_id}. Reason: {reason}",
            will="Update financial records and flag for review if pattern emerges.",
            can={"actions": ["record", "analyze", "flag"]},
            plan={
                "step_1": "Update financial records",
                "step_2": "Check for refund patterns",
                "step_3": "Flag if >3 refunds this week",
            },
        )
        
        logger.info(
            "cos_order_refunded",
            order_id=order_id,
            refund_id=refund_id,
            amount=amount,
            reason=reason,
        )
        
        return True


# Registry of all handlers
AGENT_HANDLERS = {
    "visionary": VisionaryAgentHandler,
    "sales": SalesAgentHandler,
    "chief_of_staff": ChiefOfStaffHandler,
}


async def route_event_to_handlers(event: Dict[str, Any]) -> Dict[str, bool]:
    """
    Route an event to all interested agent handlers.
    
    Args:
        event: Event dict from Redis Stream
    
    Returns:
        Dict mapping handler name to success status
    """
    results = {}
    
    for name, handler_class in AGENT_HANDLERS.items():
        handler = handler_class()
        
        # Check if handler is interested in this event
        event_type = event.get("event_type", "")
        if event_type not in handler.interested_events:
            continue
        
        try:
            success = await handler.handle_event(event)
            results[name] = success
        except Exception as e:
            logger.error(
                "handler_failed",
                handler=name,
                event_type=event_type,
                error=str(e),
            )
            results[name] = False
    
    return results
