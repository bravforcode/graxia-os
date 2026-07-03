import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import LeadMagnet, FunnelOrder, FunnelOrderItem, DigitalProduct
from app.models.contact import Contact
from app.services.funnel_delivery_service import FunnelDeliveryService
from app.services.funnel_analytics_service import FunnelAnalyticsService
from app.schemas.funnel import LeadMagnetCreate, LeadMagnetUpdate

logger = logging.getLogger(__name__)

class LeadMagnetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_lead_magnet(
        self, organization_id: uuid.UUID, payload: LeadMagnetCreate
    ) -> LeadMagnet:
        lm = LeadMagnet(
            id=uuid.uuid4(),
            organization_id=organization_id,
            name=payload.name,
            slug=payload.slug,
            target_product_id=payload.target_product_id,
            promise=payload.promise,
            file_url=payload.file_url,
            landing_page_url=payload.landing_page_url,
            status="draft",
            opt_in_count=0
        )
        self.db.add(lm)
        await self.db.commit()
        await self.db.refresh(lm)
        return lm

    async def get_lead_magnet(
        self, organization_id: uuid.UUID, lead_magnet_id: uuid.UUID
    ) -> Optional[LeadMagnet]:
        stmt = select(LeadMagnet).where(
            and_(
                LeadMagnet.id == lead_magnet_id,
                LeadMagnet.organization_id == organization_id
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_lead_magnet_by_slug(
        self, organization_id: uuid.UUID, slug: str
    ) -> Optional[LeadMagnet]:
        stmt = select(LeadMagnet).where(
            and_(
                LeadMagnet.slug == slug,
                LeadMagnet.organization_id == organization_id
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_lead_magnets(
        self, organization_id: uuid.UUID
    ) -> List[LeadMagnet]:
        stmt = select(LeadMagnet).where(LeadMagnet.organization_id == organization_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_lead_magnet(
        self, organization_id: uuid.UUID, lead_magnet_id: uuid.UUID, payload: LeadMagnetUpdate
    ) -> Optional[LeadMagnet]:
        lm = await self.get_lead_magnet(organization_id, lead_magnet_id)
        if not lm:
            return None

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(lm, field, value)

        await self.db.commit()
        await self.db.refresh(lm)
        return lm

    async def delete_lead_magnet(
        self, organization_id: uuid.UUID, lead_magnet_id: uuid.UUID
    ) -> bool:
        lm = await self.get_lead_magnet(organization_id, lead_magnet_id)
        if not lm:
            return False

        await self.db.delete(lm)
        await self.db.commit()
        return True

    async def capture_lead(
        self,
        organization_id: uuid.UUID,
        slug: str,
        email: str,
        name: Optional[str] = None,
        source: Optional[str] = None,
        medium: Optional[str] = None,
        campaign: Optional[str] = None,
        referrer: Optional[str] = None
    ) -> Tuple[Contact, Optional[str]]:
        # Find lead magnet
        lm = await self.get_lead_magnet_by_slug(organization_id, slug)
        if not lm:
            raise ValueError(f"Lead magnet not found with slug {slug} for organization {organization_id}")

        if lm.status != "published":
            raise ValueError(f"Lead magnet with slug {slug} is not published")

        # Create/Get contact
        stmt = select(Contact).where(
            and_(
                Contact.organization_id == organization_id,
                Contact.email == email,
                Contact.is_deleted == False
            )
        )
        result = await self.db.execute(stmt)
        contact = result.scalar_one_or_none()

        if not contact:
            if not name:
                name = email.split("@")[0].capitalize()
            contact = Contact(
                id=uuid.uuid4(),
                organization_id=organization_id,
                name=name,
                email=email,
                contact_type="lead",
                relationship_strength=1,
            )
            self.db.add(contact)
            await self.db.flush()

        # Increment opt-in count
        lm.opt_in_count += 1
        await self.db.flush()

        # Log lead capture conversion event
        analytics_service = FunnelAnalyticsService(self.db)
        await analytics_service.log_event(
            organization_id=organization_id,
            event_type="lead_capture",
            product_id=lm.target_product_id,
            contact_id=contact.id,
            session_id=None,
            source=source,
            medium=medium,
            campaign=campaign,
            referrer=referrer,
            metadata_json={"lead_magnet_id": str(lm.id), "lead_magnet_slug": slug}
        )

        raw_token = None
        if lm.target_product_id:
            # Grant free digital asset delivery access
            order = FunnelOrder(
                id=uuid.uuid4(),
                organization_id=organization_id,
                contact_id=contact.id,
                status="paid",
                subtotal_amount=Decimal("0.00"),
                total_amount=Decimal("0.00"),
                currency="USD",
                customer_email=email,
                paid_at=datetime.utcnow()
            )
            self.db.add(order)
            await self.db.flush()

            item = FunnelOrderItem(
                id=uuid.uuid4(),
                organization_id=organization_id,
                order_id=order.id,
                product_id=lm.target_product_id,
                quantity=1,
                unit_amount=Decimal("0.00"),
                total_amount=Decimal("0.00"),
                currency="USD"
            )
            self.db.add(item)
            await self.db.flush()

            # Grant delivery access using FunnelDeliveryService
            delivery_service = FunnelDeliveryService(self.db)
            access_grants = await delivery_service.grant_delivery_access_for_order(
                organization_id=organization_id,
                order_id=order.id
            )
            
            if access_grants:
                raw_token = access_grants[0][1]

        await self.db.commit()
        await self.db.refresh(contact)

        return contact, raw_token
