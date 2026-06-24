import logging
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.funnel import FunnelOrder, FunnelOrderItem, DeliveryAsset, DeliveryAccess, DigitalProduct

logger = logging.getLogger(__name__)

class FunnelDeliveryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _generate_token(self) -> str:
        return secrets.token_urlsafe(32)

    async def grant_delivery_access_for_order(
        self, organization_id: UUID, order_id: UUID, 
        expires_in_days: int = 30, max_downloads: int = 10
    ) -> List[Tuple[DeliveryAccess, str]]:
        """
        Grant delivery access for all products in a paid order.
        Returns a list of (DeliveryAccess, raw_token) tuples.
        """
        # Load order
        stmt = select(FunnelOrder).where(
            and_(
                FunnelOrder.id == order_id,
                FunnelOrder.organization_id == organization_id
            )
        )
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()

        if not order:
            logger.error(f"Order {order_id} not found for org {organization_id}")
            return []
        
        if order.status != "paid":
            logger.warning(f"Attempted to grant delivery for unpaid order {order_id}")
            return []

        # Load order items
        stmt = select(FunnelOrderItem).where(FunnelOrderItem.order_id == order_id)
        result = await self.db.execute(stmt)
        items = result.scalars().all()

        results = []
        expires_at = datetime.now() + timedelta(days=expires_in_days)

        for item in items:
            # Find active delivery assets for this product
            stmt = select(DeliveryAsset).where(
                and_(
                    DeliveryAsset.product_id == item.product_id,
                    DeliveryAsset.organization_id == organization_id,
                    DeliveryAsset.is_active == True
                )
            )
            res = await self.db.execute(stmt)
            assets = res.scalars().all()

            for asset in assets:
                # Idempotency check: Does access already exist for this order/asset?
                stmt = select(DeliveryAccess).where(
                    and_(
                        DeliveryAccess.order_id == order_id,
                        DeliveryAccess.asset_id == asset.id
                    )
                )
                res = await self.db.execute(stmt)
                existing = res.scalar_one_or_none()
                
                if existing:
                    logger.info(f"Delivery access already exists for order {order_id} asset {asset.id}")
                    continue

                raw_token = self._generate_token()
                access = DeliveryAccess(
                    organization_id=organization_id,
                    order_id=order_id,
                    product_id=item.product_id,
                    asset_id=asset.id,
                    access_token_hash=self._hash_token(raw_token),
                    status="active",
                    max_downloads=max_downloads,
                    expires_at=expires_at,
                    download_count=0
                )
                self.db.add(access)
                results.append((access, raw_token))

        if results:
            await self.db.commit()
            for access, _ in results:
                await self.db.refresh(access)
        
        return results

    async def get_delivery_access_by_token(self, raw_token: str) -> Optional[DeliveryAccess]:
        """
        Retrieve delivery access by raw token.
        Validates expiry and max downloads.
        Increments download count on success.
        """
        token_hash = self._hash_token(raw_token)
        stmt = select(DeliveryAccess).where(
            and_(
                DeliveryAccess.access_token_hash == token_hash,
                DeliveryAccess.status == "active"
            )
        )
        result = await self.db.execute(stmt)
        access = result.scalar_one_or_none()

        if not access:
            return None

        # Validation
        if access.expires_at and access.expires_at < datetime.now():
            logger.warning(f"Access token {token_hash[:8]} expired at {access.expires_at}")
            return None
        
        if access.max_downloads and access.download_count >= access.max_downloads:
            logger.warning(f"Access token {token_hash[:8]} reached max downloads ({access.max_downloads})")
            return None

        # Record access
        access.download_count += 1
        if access.first_accessed_at is None:
            access.first_accessed_at = datetime.now()
        access.last_accessed_at = datetime.now()
        
        await self.db.commit()
        await self.db.refresh(access)
        
        return access

    async def list_order_delivery_accesses(self, organization_id: UUID, order_id: UUID) -> List[DeliveryAccess]:
        stmt = select(DeliveryAccess).where(
            and_(
                DeliveryAccess.order_id == order_id,
                DeliveryAccess.organization_id == organization_id
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_delivery_payload(self, access: DeliveryAccess) -> dict:
        """Construct safe delivery payload for the customer."""
        # Load asset info
        stmt = select(DeliveryAsset).where(DeliveryAsset.id == access.asset_id)
        result = await self.db.execute(stmt)
        asset = result.scalar_one_or_none()
        
        if not asset:
            return {}
            
        # Load product info
        stmt = select(DigitalProduct).where(DigitalProduct.id == asset.product_id)
        result = await self.db.execute(stmt)
        product = result.scalar_one_or_none()
        
        if not product:
            return {}
        
        payload = {
            "product_name": product.name,
            "asset_title": asset.title,
            "asset_type": asset.asset_type,
            "expires_at": access.expires_at,
            "downloads_remaining": (access.max_downloads - access.download_count) if access.max_downloads else None
        }
        
        # Safe content exposure
        if asset.asset_type in ["text", "private_page"]:
            payload["content_body"] = asset.content_body
        elif asset.asset_type == "external_link":
            payload["external_url"] = asset.external_url
            
        return payload
