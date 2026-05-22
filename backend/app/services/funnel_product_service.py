import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import DigitalProduct, DeliveryAsset
from app.schemas.funnel import (
    DigitalProductCreate,
    DigitalProductUpdate,
    DeliveryAssetCreate,
    DeliveryAssetUpdate,
)

logger = logging.getLogger(__name__)

class FunnelProductService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_product(
        self, organization_id: UUID, payload: DigitalProductCreate
    ) -> DigitalProduct:
        product = DigitalProduct(
            **payload.model_dump(),
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
            DigitalProduct.is_deleted == False,
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
                DigitalProduct.is_deleted == False,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_product(
        self, organization_id: UUID, product_id: UUID, payload: DigitalProductUpdate
    ) -> Optional[DigitalProduct]:
        product = await self.get_product(organization_id, product_id)
        if not product:
            return None

        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(product, key, value)

        await self.db.commit()
        await self.db.refresh(product)
        logger.info(f"Product {product_id} updated for org {organization_id}")
        return product

    async def publish_product(
        self, organization_id: UUID, product_id: UUID
    ) -> Optional[DigitalProduct]:
        product = await self.get_product(organization_id, product_id)
        if not product:
            return None

        # Validation for publishing
        if not product.slug or product.price_amount < 0:
            logger.warning(f"Publish validation failed for product {product_id}: invalid slug or price")
            return None

        # At least one active asset check
        stmt = select(DeliveryAsset).where(
            and_(
                DeliveryAsset.product_id == product_id,
                DeliveryAsset.is_active == True,
            )
        )
        assets_result = await self.db.execute(stmt)
        if not assets_result.scalars().first():
            logger.warning(f"Publish validation failed for product {product_id}: no active assets")
            # For now, we will allow publishing but log a warning.
            # Some products might be pure "service" products or handled differently.

        product.status = "published"
        product.published_at = datetime.now()
        await self.db.commit()
        await self.db.refresh(product)
        logger.info(f"Product {product_id} published for org {organization_id}")
        return product

    async def archive_product(
        self, organization_id: UUID, product_id: UUID
    ) -> Optional[DigitalProduct]:
        product = await self.get_product(organization_id, product_id)
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
        product = await self.get_product(organization_id, product_id)
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
        product = await self.get_product(organization_id, product_id)
        if not product:
            return None

        asset = DeliveryAsset(
            **payload.model_dump(),
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
        asset = await self.get_delivery_asset(organization_id, asset_id)
        if not asset:
            return None

        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(asset, key, value)

        await self.db.commit()
        await self.db.refresh(asset)
        logger.info(f"Delivery asset {asset_id} updated for org {organization_id}")
        return asset

    async def deactivate_delivery_asset(
        self, organization_id: UUID, asset_id: UUID
    ) -> bool:
        asset = await self.get_delivery_asset(organization_id, asset_id)
        if not asset:
            return False

        asset.is_active = False
        await self.db.commit()
        logger.info(f"Delivery asset {asset_id} deactivated for org {organization_id}")
        return True
