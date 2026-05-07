"""
Revenue OS Outbox Service
Transactional Outbox pattern for guaranteed event delivery (HR-07)

All domain events are written to the outbox in the same DB transaction
as business state changes. Celery workers poll and publish to Redis Streams.
"""
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime
import json
import structlog

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import OutboxEvent

logger = structlog.get_logger()


class OutboxService:
    """
    Transactional Outbox Service
    
    Guarantees event delivery by writing events atomically with business changes.
    Events are picked up by Celery workers and published to Redis Streams.
    """

    @staticmethod
    async def publish_event(
        db: AsyncSession,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> OutboxEvent:
        """
        Publish an event to the outbox.
        
        This must be called within the same transaction as business operations
        to guarantee atomicity (HR-07).
        
        Args:
            db: Database session (must be in active transaction)
            aggregate_type: Type of aggregate (order, lead, campaign, etc.)
            aggregate_id: Aggregate UUID as string
            event_type: Event type identifier
            payload: Event data (must be JSON serializable)
            headers: Optional message headers
            correlation_id: Optional correlation ID for distributed tracing
            causation_id: Optional causation ID for event sourcing
        
        Returns:
            OutboxEvent: The created outbox event
        """
        event = OutboxEvent(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            headers=headers or {},
            correlation_id=correlation_id,
            causation_id=causation_id,
            processed=False,
            retry_count=0,
        )
        db.add(event)
        await db.flush()
        
        logger.debug(
            "outbox_event_published",
            event_id=str(event.id),
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
        )
        
        return event

    @staticmethod
    async def publish_order_created(
        db: AsyncSession,
        order_id: UUID,
        customer_email: str,
        amount_cents: int,
        currency: str,
        platform: str,
        product_id: UUID,
        correlation_id: Optional[str] = None,
    ) -> OutboxEvent:
        """Publish order created event."""
        return await OutboxService.publish_event(
            db=db,
            aggregate_type="order",
            aggregate_id=str(order_id),
            event_type="order_created",
            payload={
                "order_id": str(order_id),
                "customer_email": customer_email,
                "amount_cents": amount_cents,
                "currency": currency,
                "platform": platform,
                "product_id": str(product_id),
                "created_at": datetime.utcnow().isoformat(),
            },
            correlation_id=correlation_id,
        )

    @staticmethod
    async def publish_order_fulfilled(
        db: AsyncSession,
        order_id: UUID,
        customer_email: str,
        product_name: str,
        fulfillment_url: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> OutboxEvent:
        """Publish order fulfilled event."""
        return await OutboxService.publish_event(
            db=db,
            aggregate_type="order",
            aggregate_id=str(order_id),
            event_type="order_fulfilled",
            payload={
                "order_id": str(order_id),
                "customer_email": customer_email,
                "product_name": product_name,
                "fulfillment_url": fulfillment_url,
                "fulfilled_at": datetime.utcnow().isoformat(),
            },
            correlation_id=correlation_id,
        )

    @staticmethod
    async def publish_order_refunded(
        db: AsyncSession,
        order_id: UUID,
        refund_id: UUID,
        amount_cents: int,
        currency: str,
        reason: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> OutboxEvent:
        """Publish order refunded event."""
        return await OutboxService.publish_event(
            db=db,
            aggregate_type="order",
            aggregate_id=str(order_id),
            event_type="order_refunded",
            payload={
                "order_id": str(order_id),
                "refund_id": str(refund_id),
                "amount_cents": amount_cents,
                "currency": currency,
                "reason": reason,
                "refunded_at": datetime.utcnow().isoformat(),
            },
            correlation_id=correlation_id,
        )

    @staticmethod
    async def publish_lead_identified(
        db: AsyncSession,
        lead_id: UUID,
        email: str,
        source: str,
        score: int,
        correlation_id: Optional[str] = None,
    ) -> OutboxEvent:
        """Publish lead identified event."""
        return await OutboxService.publish_event(
            db=db,
            aggregate_type="lead",
            aggregate_id=str(lead_id),
            event_type="lead_identified",
            payload={
                "lead_id": str(lead_id),
                "email": email,
                "source": source,
                "score": score,
                "identified_at": datetime.utcnow().isoformat(),
            },
            correlation_id=correlation_id,
        )

    @staticmethod
    async def publish_lead_converted(
        db: AsyncSession,
        lead_id: UUID,
        order_id: UUID,
        customer_email: str,
        amount_cents: int,
        correlation_id: Optional[str] = None,
    ) -> OutboxEvent:
        """Publish lead converted event."""
        return await OutboxService.publish_event(
            db=db,
            aggregate_type="lead",
            aggregate_id=str(lead_id),
            event_type="lead_converted",
            payload={
                "lead_id": str(lead_id),
                "order_id": str(order_id),
                "customer_email": customer_email,
                "amount_cents": amount_cents,
                "converted_at": datetime.utcnow().isoformat(),
            },
            correlation_id=correlation_id,
        )

    @staticmethod
    async def publish_approval_required(
        db: AsyncSession,
        approval_id: UUID,
        approval_type: str,
        requested_by: str,
        priority: str = "normal",
        metadata: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> OutboxEvent:
        """Publish approval required event."""
        return await OutboxService.publish_event(
            db=db,
            aggregate_type="approval",
            aggregate_id=str(approval_id),
            event_type="approval_required",
            payload={
                "approval_id": str(approval_id),
                "approval_type": approval_type,
                "requested_by": requested_by,
                "priority": priority,
                "metadata": metadata or {},
                "requested_at": datetime.utcnow().isoformat(),
            },
            correlation_id=correlation_id,
        )

    @staticmethod
    async def publish_campaign_created(
        db: AsyncSession,
        campaign_id: UUID,
        campaign_name: str,
        objective: str,
        budget_cents: int,
        target_revenue_cents: int,
        correlation_id: Optional[str] = None,
    ) -> OutboxEvent:
        """Publish campaign created event."""
        return await OutboxService.publish_event(
            db=db,
            aggregate_type="campaign",
            aggregate_id=str(campaign_id),
            event_type="campaign_created",
            payload={
                "campaign_id": str(campaign_id),
                "campaign_name": campaign_name,
                "objective": objective,
                "budget_cents": budget_cents,
                "target_revenue_cents": target_revenue_cents,
                "created_at": datetime.utcnow().isoformat(),
            },
            correlation_id=correlation_id,
        )

    @staticmethod
    async def publish_campaign_target_hit(
        db: AsyncSession,
        campaign_id: UUID,
        campaign_name: str,
        target_revenue_cents: int,
            actual_revenue_cents: int,
        correlation_id: Optional[str] = None,
    ) -> OutboxEvent:
        """Publish campaign target hit event."""
        return await OutboxService.publish_event(
            db=db,
            aggregate_type="campaign",
            aggregate_id=str(campaign_id),
            event_type="campaign_target_hit",
            payload={
                "campaign_id": str(campaign_id),
                "campaign_name": campaign_name,
                "target_revenue_cents": target_revenue_cents,
                "actual_revenue_cents": actual_revenue_cents,
                "hit_at": datetime.utcnow().isoformat(),
            },
            correlation_id=correlation_id,
        )

    @staticmethod
    async def publish_incident_created(
        db: AsyncSession,
        incident_id: UUID,
        severity: str,
        title: str,
        description: str,
        affected_campaign_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> OutboxEvent:
        """Publish incident created event."""
        payload = {
            "incident_id": str(incident_id),
            "severity": severity,
            "title": title,
            "description": description,
            "created_at": datetime.utcnow().isoformat(),
        }
        if affected_campaign_id:
            payload["affected_campaign_id"] = str(affected_campaign_id)
        
        return await OutboxService.publish_event(
            db=db,
            aggregate_type="incident",
            aggregate_id=str(incident_id),
            event_type="incident_created",
            payload=payload,
            correlation_id=correlation_id,
        )
