"""
Revenue OS Fulfillment Service
Order fulfillment and entitlement management
"""
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta
import structlog

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Order, Product, Entitlement, DeliveryEvent
from ..enums import OrderStatus, DeliveryStatus
from ..core.db_ops import atomic_operation
from .email_service import EmailService

logger = structlog.get_logger()


class FulfillmentService:
    """
    Order fulfillment service.
    Handles product delivery, entitlement grants, and delivery notifications.
    """
    
    @staticmethod
    async def fulfill_order(
        db: AsyncSession,
        order_id: UUID,
        auto_queue_email: bool = True,
    ) -> DeliveryEvent:
        """
        Fulfill an order: grant entitlement and queue delivery email.
        
        Args:
            db: Database session
            order_id: Order ID to fulfill
            auto_queue_email: Whether to automatically queue delivery email
        
        Returns:
            DeliveryEvent: Delivery event record
        
        Raises:
            ValueError: If order not found or already fulfilled
        """
        async with atomic_operation(db):
            # Get order with product
            order_result = await db.execute(
                select(Order).where(Order.id == order_id)
            )
            order = order_result.scalar_one_or_none()
            
            if not order:
                raise ValueError(f"Order {order_id} not found")
            
            if order.delivery_status == DeliveryStatus.DELIVERED:
                logger.info("order_already_fulfilled", order_id=str(order_id))
                # Return existing delivery event
                event_result = await db.execute(
                    select(DeliveryEvent)
                    .where(DeliveryEvent.order_id == order_id)
                    .order_by(DeliveryEvent.created_at.desc())
                )
                return event_result.scalar_one()
            
            # Get product
            product_result = await db.execute(
                select(Product).where(Product.id == order.product_id)
            )
            product = product_result.scalar_one_or_none()
            
            if not product:
                raise ValueError(f"Product {order.product_id} not found")
            
            # Create entitlement
            entitlement = await FulfillmentService.create_entitlement(
                db=db,
                order_id=order_id,
                customer_email=order.customer_email,
                product_key=product.slug,
            )
            
            # Create delivery event
            delivery_event = DeliveryEvent(
                order_id=order_id,
                customer_id=order.customer_id,
                event_type="product_delivered",
                delivery_type="email_access",
                status=DeliveryStatus.QUEUED,
                message=f"Entitlement granted for {product.name}",
            )
            db.add(delivery_event)
            await db.flush()
            
            # Queue delivery email if enabled
            if auto_queue_email:
                email = await EmailService.queue_delivery_email(
                    db=db,
                    order_id=order_id,
                    product_name=product.name,
                    fulfillment_url=product.fulfillment_url,
                    fulfillment_instructions=product.fulfillment_instructions,
                )
                delivery_event.email_outbox_id = email.id
            
            # Update order delivery status
            order.delivery_status = DeliveryStatus.PENDING
            
            await db.commit()
            
            logger.info(
                "order_fulfilled",
                order_id=str(order_id),
                product_id=str(product.id),
                entitlement_id=str(entitlement.id),
                delivery_event_id=str(delivery_event.id),
            )
            
            return delivery_event
    
    @staticmethod
    async def create_entitlement(
        db: AsyncSession,
        order_id: UUID,
        customer_email: str,
        product_key: str,
        expires_at: Optional[datetime] = None,
    ) -> Entitlement:
        """
        Grant product entitlement to customer.
        
        Args:
            db: Database session
            order_id: Order ID
            customer_email: Customer email
            product_key: Product key/slug
            expires_at: Optional expiration date
        
        Returns:
            Entitlement: Created entitlement
        """
        entitlement = Entitlement(
            order_id=order_id,
            customer_email=customer_email,
            product_key=product_key,
            expires_at=expires_at,
        )
        db.add(entitlement)
        await db.flush()
        
        logger.info(
            "entitlement_granted",
            entitlement_id=str(entitlement.id),
            customer_email=customer_email,
            product_key=product_key,
        )
        
        return entitlement
    
    @staticmethod
    async def revoke_entitlement(
        db: AsyncSession,
        entitlement_id: UUID,
    ) -> Entitlement:
        """
        Revoke a customer entitlement.
        
        Args:
            db: Database session
            entitlement_id: Entitlement ID to revoke
        
        Returns:
            Entitlement: Revoked entitlement
        """
        result = await db.execute(
            select(Entitlement).where(Entitlement.id == entitlement_id)
        )
        entitlement = result.scalar_one_or_none()
        
        if not entitlement:
            raise ValueError(f"Entitlement {entitlement_id} not found")
        
        entitlement.revoked_at = datetime.utcnow()
        await db.commit()
        
        logger.info(
            "entitlement_revoked",
            entitlement_id=str(entitlement_id),
            customer_email=entitlement.customer_email,
        )
        
        return entitlement
    
    @staticmethod
    async def verify_delivery(
        db: AsyncSession,
        order_id: UUID,
    ) -> bool:
        """
        Verify that an order has been delivered.
        
        Args:
            db: Database session
            order_id: Order ID to verify
        
        Returns:
            bool: True if delivered, False otherwise
        """
        # Check for delivery event
        result = await db.execute(
            select(DeliveryEvent)
            .where(
                DeliveryEvent.order_id == order_id,
                DeliveryEvent.status == DeliveryStatus.DELIVERED,
            )
        )
        delivery_event = result.scalar_one_or_none()
        
        if delivery_event:
            return True
        
        # Check for entitlement
        order_result = await db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = order_result.scalar_one_or_none()
        
        if not order:
            return False
        
        entitlement_result = await db.execute(
            select(Entitlement)
            .where(
                Entitlement.order_id == order_id,
                Entitlement.revoked_at.is_(None),
            )
        )
        entitlement = entitlement_result.scalar_one_or_none()
        
        return entitlement is not None
    
    @staticmethod
    async def mark_delivery_complete(
        db: AsyncSession,
        delivery_event_id: UUID,
    ) -> DeliveryEvent:
        """
        Mark a delivery event as complete.
        
        Args:
            db: Database session
            delivery_event_id: Delivery event ID
        
        Returns:
            DeliveryEvent: Updated delivery event
        """
        result = await db.execute(
            select(DeliveryEvent).where(DeliveryEvent.id == delivery_event_id)
        )
        delivery_event = result.scalar_one_or_none()
        
        if not delivery_event:
            raise ValueError(f"Delivery event {delivery_event_id} not found")
        
        delivery_event.status = DeliveryStatus.DELIVERED
        delivery_event.delivered_at = datetime.utcnow()
        
        # Update order delivery status
        order_result = await db.execute(
            select(Order).where(Order.id == delivery_event.order_id)
        )
        order = order_result.scalar_one_or_none()
        if order:
            order.delivery_status = DeliveryStatus.DELIVERED
        
        await db.commit()
        
        logger.info(
            "delivery_marked_complete",
            delivery_event_id=str(delivery_event_id),
            order_id=str(delivery_event.order_id),
        )
        
        return delivery_event
    
    @staticmethod
    async def get_customer_entitlements(
        db: AsyncSession,
        customer_email: str,
    ) -> list[Entitlement]:
        """
        Get all active entitlements for a customer.
        
        Args:
            db: Database session
            customer_email: Customer email
        
        Returns:
            list[Entitlement]: List of active entitlements
        """
        now = datetime.utcnow()
        
        result = await db.execute(
            select(Entitlement)
            .where(
                Entitlement.customer_email == customer_email,
                Entitlement.revoked_at.is_(None),
                (Entitlement.expires_at.is_(None)) | (Entitlement.expires_at > now),
            )
        )
        
        return list(result.scalars().all())
