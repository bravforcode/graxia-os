import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import (
    DeliveryAsset,
    DigitalProduct,
    FunnelCheckoutSession,
)
from app.schemas.funnel import (
    DigitalProductCreate,
    DigitalProductUpdate,
    DeliveryAssetCreate,
    DeliveryAssetUpdate,
)

logger = logging.getLogger(__name__)


OPEN_CHECKOUT_STATUSES = ("created", "pending")


class FunnelProductConflictError(Exception):
    """Raised when a product or asset change would break fulfillment."""


class FunnelProductService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _lock_product(
        self, organization_id: UUID, product_id: UUID
    ) -> Optional[DigitalProduct]:
        result = await self.db.execute(
            select(DigitalProduct)
            .where(
                DigitalProduct.id == product_id,
                DigitalProduct.organization_id == organization_id,
                DigitalProduct.is_deleted.is_not(True),
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def _active_asset_count(
        self, organization_id: UUID, product_id: UUID
    ) -> int:
        count = await self.db.scalar(
            select(func.count(DeliveryAsset.id)).where(
                DeliveryAsset.organization_id == organization_id,
                DeliveryAsset.product_id == product_id,
                DeliveryAsset.is_active.is_(True),
            )
        )
        return int(count or 0)

    async def _has_open_checkout(
        self, organization_id: UUID, product_id: UUID
    ) -> bool:
        checkout_id = await self.db.scalar(
            select(FunnelCheckoutSession.id)
            .where(
                FunnelCheckoutSession.organization_id == organization_id,
                FunnelCheckoutSession.product_id == product_id,
                FunnelCheckoutSession.status.in_(OPEN_CHECKOUT_STATUSES),
            )
            .limit(1)
        )
        return checkout_id is not None

    async def _require_active_asset(
        self, organization_id: UUID, product_id: UUID
    ) -> None:
        if await self._active_asset_count(organization_id, product_id) == 0:
            raise FunnelProductConflictError(
                "Product cannot be published without an active delivery asset"
            )

    async def _lock_delivery_asset(
        self, organization_id: UUID, product_id: UUID, asset_id: UUID
    ) -> Optional[DeliveryAsset]:
        result = await self.db.execute(
            select(DeliveryAsset)
            .where(
                DeliveryAsset.id == asset_id,
                DeliveryAsset.organization_id == organization_id,
                DeliveryAsset.product_id == product_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def _ensure_asset_can_be_deactivated(
        self, product: DigitalProduct
    ) -> None:
        if await self._has_open_checkout(product.organization_id, product.id):
            raise FunnelProductConflictError(
                "Cannot deactivate a delivery asset while a checkout is in progress"
            )
        if (
            product.status == "published"
            and await self._active_asset_count(product.organization_id, product.id) <= 1
        ):
            raise FunnelProductConflictError(
                "A published product must retain at least one active delivery asset"
            )

    async def create_product(
        self, organization_id: UUID, payload: DigitalProductCreate
    ) -> DigitalProduct:
        product = DigitalProduct(
            **payload.model_dump(exclude={"organization_id"}),
            organization_id=organization_id,
        )
        self.db.add(product)
        await self.db.commit()
        await self.db.refresh(product)
        logger.info(f"Product {product.id} created for org {organization_id}")
        return product

    async def list_products(
        self, 
        organization_id: UUID, 
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> List[DigitalProduct]:
        filters = [
            DigitalProduct.organization_id == organization_id,
            DigitalProduct.is_deleted.is_(False),
        ]
        if not include_archived:
            filters.append(DigitalProduct.status != "archived")
            
        stmt = (
            select(DigitalProduct)
            .where(and_(*filters))
            .limit(limit)
            .offset(offset)
            .order_by(DigitalProduct.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_product(
        self, organization_id: UUID, product_id: UUID
    ) -> Optional[DigitalProduct]:
        stmt = select(DigitalProduct).where(
            and_(
                DigitalProduct.id == product_id,
                DigitalProduct.organization_id == organization_id,
                DigitalProduct.is_deleted.is_(False),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_product_by_slug(
        self, organization_id: UUID, slug: str
    ) -> Optional[DigitalProduct]:
        stmt = select(DigitalProduct).where(
            and_(
                DigitalProduct.slug == slug,
                DigitalProduct.organization_id == organization_id,
                DigitalProduct.is_deleted.is_(False),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_product(
        self, organization_id: UUID, product_id: UUID, payload: DigitalProductUpdate
    ) -> Optional[DigitalProduct]:
        product = await self._lock_product(organization_id, product_id)
        if not product:
            return None

        update_data = payload.model_dump(exclude_unset=True)
        if update_data.get("status") == "published":
            await self._require_active_asset(organization_id, product_id)
        for key, value in update_data.items():
            setattr(product, key, value)

        await self.db.commit()
        await self.db.refresh(product)
        logger.info(f"Product {product_id} updated for org {organization_id}")
        return product

    async def publish_product(
        self, organization_id: UUID, product_id: UUID
    ) -> Optional[DigitalProduct]:
        product = await self._lock_product(organization_id, product_id)
        if not product:
            return None

        # Validation for publishing
        if not product.slug or product.price_amount < 0:
            logger.warning(f"Publish validation failed for product {product_id}: invalid slug or price")
            return None

        await self._require_active_asset(organization_id, product_id)

        product.status = "published"
        product.published_at = datetime.now()
        await self.db.commit()
        await self.db.refresh(product)
        logger.info(f"Product {product_id} published for org {organization_id}")
        return product

    async def archive_product(
        self, organization_id: UUID, product_id: UUID
    ) -> Optional[DigitalProduct]:
        product = await self._lock_product(organization_id, product_id)
        if not product:
            return None

        product.status = "archived"
        await self.db.commit()
        await self.db.refresh(product)
        logger.info(f"Product {product_id} archived for org {organization_id}")
        return product

    async def delete_or_soft_delete_product(
        self, organization_id: UUID, product_id: UUID
    ) -> bool:
        product = await self._lock_product(organization_id, product_id)
        if not product:
            return False

        product.is_deleted = True
        product.deleted_at = datetime.now()
        await self.db.commit()
        logger.info(f"Product {product_id} soft-deleted for org {organization_id}")
        return True

    # Delivery Asset Methods
    async def create_delivery_asset(
        self, organization_id: UUID, product_id: UUID, payload: DeliveryAssetCreate
    ) -> Optional[DeliveryAsset]:
        # Verify product ownership
        product = await self._lock_product(organization_id, product_id)
        if not product:
            return None

        asset = DeliveryAsset(
            **payload.model_dump(exclude={"product_id", "organization_id"}),
            product_id=product_id,
            organization_id=organization_id,
        )
        self.db.add(asset)
        await self.db.commit()
        await self.db.refresh(asset)
        logger.info(f"Delivery asset {asset.id} created for product {product_id} in org {organization_id}")
        return asset

    async def list_delivery_assets(
        self, organization_id: UUID, product_id: UUID
    ) -> List[DeliveryAsset]:
        # Verify product ownership
        product = await self.get_product(organization_id, product_id)
        if not product:
            return []

        stmt = select(DeliveryAsset).where(
            and_(
                DeliveryAsset.product_id == product_id,
                DeliveryAsset.organization_id == organization_id,
            )
        ).order_by(DeliveryAsset.created_at.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_delivery_asset(
        self, organization_id: UUID, asset_id: UUID
    ) -> Optional[DeliveryAsset]:
        stmt = select(DeliveryAsset).where(
            and_(
                DeliveryAsset.id == asset_id,
                DeliveryAsset.organization_id == organization_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_delivery_asset(
        self, organization_id: UUID, asset_id: UUID, payload: DeliveryAssetUpdate
    ) -> Optional[DeliveryAsset]:
        existing_asset = await self.get_delivery_asset(organization_id, asset_id)
        if not existing_asset:
            return None

        product = await self._lock_product(organization_id, existing_asset.product_id)
        if not product:
            return None
        asset = await self._lock_delivery_asset(
            organization_id, existing_asset.product_id, asset_id
        )
        if not asset:
            return None

        update_data = payload.model_dump(exclude_unset=True)
        if update_data.get("is_active") is False and asset.is_active:
            await self._ensure_asset_can_be_deactivated(product)
        for key, value in update_data.items():
            setattr(asset, key, value)

        await self.db.commit()
        await self.db.refresh(asset)
        logger.info(f"Delivery asset {asset_id} updated for org {organization_id}")
        return asset

    async def deactivate_delivery_asset(
        self, organization_id: UUID, asset_id: UUID
    ) -> bool:
        asset = await self.update_delivery_asset(
            organization_id, asset_id, DeliveryAssetUpdate(is_active=False)
        )
        if asset is None:
            return False
        logger.info(f"Delivery asset {asset_id} deactivated for org {organization_id}")
        return True
