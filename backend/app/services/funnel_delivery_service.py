import logging
import secrets
import hashlib
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import List, Optional, Tuple
from uuid import UUID
from urllib.parse import urlsplit

from sqlalchemy import select, and_, exists, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.funnel import (
    DeliveryAccess,
    DeliveryAsset,
    DigitalProduct,
    FunnelOrder,
    FunnelOrderItem,
    LeadMagnet,
)

logger = logging.getLogger(__name__)

class FunnelDeliveryService:
    STORAGE_ROOT_ENV = "FUNNEL_DELIVERY_STORAGE_ROOT"
    LEAD_MAGNET_STORAGE_ROOT_ENV = "FUNNEL_LEAD_MAGNET_STORAGE_ROOT"

    def __init__(self, db: AsyncSession):
        self.db = db

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _generate_token(self) -> str:
        return secrets.token_urlsafe(32)

    @classmethod
    def resolve_storage_file(
        cls, storage_path: Optional[str], storage_root: Optional[str] = None
    ) -> Optional[Path]:
        """Resolve a relative asset path only beneath an existing configured root."""
        root_value = storage_root or os.environ.get(cls.STORAGE_ROOT_ENV)
        if not root_value or not storage_path or "\x00" in storage_path:
            return None

        normalized = storage_path.replace("\\", "/")
        windows_path = PureWindowsPath(storage_path)
        relative = PurePosixPath(normalized)
        if (
            Path(root_value).is_absolute() is False
            or windows_path.is_absolute()
            or windows_path.drive
            or relative.is_absolute()
            or any(part in {".", ".."} for part in relative.parts)
        ):
            return None

        try:
            root = Path(root_value).resolve(strict=True)
            if not root.is_dir():
                return None
            candidate = (root.joinpath(*relative.parts)).resolve(strict=True)
            candidate.relative_to(root)
            return candidate if candidate.is_file() else None
        except (OSError, RuntimeError, ValueError):
            return None

    @classmethod
    def resolve_lead_magnet_storage_file(
        cls, storage_path: Optional[str]
    ) -> Optional[Path]:
        """Resolve only designated non-HTML files beneath the lead-magnet root."""
        package_root = Path(__file__).resolve().parents[2] / "assets" / "lead_magnets"
        root_value = os.environ.get(cls.LEAD_MAGNET_STORAGE_ROOT_ENV) or str(
            package_root
        )
        try:
            root = Path(root_value).resolve(strict=True)
            if not root.is_dir() or root.name.casefold() != "lead_magnets":
                return None
        except (OSError, RuntimeError, ValueError):
            return None
        resolved = cls.resolve_storage_file(storage_path, str(root))
        if resolved and resolved.suffix.lower() in {".html", ".htm", ".xhtml"}:
            return None
        return resolved

    @classmethod
    def asset_has_verified_payload(cls, asset: DeliveryAsset) -> bool:
        """Fail closed unless an explicitly assigned asset has a local payload."""
        if not asset.is_active:
            return False
        if asset.asset_type == "file":
            return cls.resolve_lead_magnet_storage_file(asset.storage_path) is not None
        if asset.asset_type in {"text", "content", "private_page"}:
            return bool(asset.content_body and asset.content_body.strip())
        # Public lead-magnet delivery does not follow unverified external URLs.
        return False

    async def grant_delivery_access_for_order(
        self, organization_id: UUID, order_id: UUID, 
        expires_in_days: int = 30, max_downloads: int = 10,
        commit: bool = True,
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
        ).with_for_update()
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()

        if not order:
            logger.error(f"Order {order_id} not found for org {organization_id}")
            if commit:
                await self.db.commit()
            return []
        
        if order.status != "paid" or order.refunded_at is not None:
            logger.warning(
                f"Attempted to grant delivery for ineligible order {order_id}"
            )
            if commit:
                await self.db.commit()
            return []

        # Load order items
        stmt = select(FunnelOrderItem).where(FunnelOrderItem.order_id == order_id)
        result = await self.db.execute(stmt)
        items = result.scalars().all()

        results = []
        expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)

        for item in items:
            # Find active delivery assets for this product
            stmt = select(DeliveryAsset).where(
                and_(
                    DeliveryAsset.product_id == item.product_id,
                    DeliveryAsset.organization_id == organization_id,
                    DeliveryAsset.is_active.is_(True)
                )
            )
            res = await self.db.execute(stmt)
            assets = res.scalars().all()

            for asset in assets:
                # Idempotency check: Does access already exist for this order/asset?
                stmt = select(DeliveryAccess).where(
                    and_(
                        DeliveryAccess.order_id == order_id,
                        or_(
                            DeliveryAccess.asset_id == asset.id,
                            DeliveryAccess.delivery_asset_id == asset.id,
                        ),
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
                    delivery_asset_id=asset.id,
                    access_token_hash=self._hash_token(raw_token),
                    status="active",
                    max_downloads=max_downloads,
                    expires_at=expires_at,
                    download_count=0
                )
                self.db.add(access)
                results.append((access, raw_token))

        if commit:
            await self.db.commit()
            for access, _ in results:
                await self.db.refresh(access)
        elif results:
            await self.db.flush()
        
        return results

    async def get_delivery_access_by_token(self, raw_token: str) -> Optional[DeliveryAccess]:
        """
        Validate a token without recording a download.
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
        expires_at = access.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at and expires_at <= datetime.now(UTC):
            logger.warning(f"Access token {token_hash[:8]} expired at {access.expires_at}")
            return None
        
        if (
            access.max_downloads is not None
            and access.download_count >= access.max_downloads
        ):
            logger.warning(f"Access token {token_hash[:8]} reached max downloads ({access.max_downloads})")
            return None

        order = await self.db.scalar(
            select(FunnelOrder).where(
                FunnelOrder.id == access.order_id,
                FunnelOrder.organization_id == access.organization_id,
            )
        )
        if order is None or order.refunded_at is not None:
            return None

        return access

    async def consume_delivery_access(
        self, access: DeliveryAccess
    ) -> Optional[DeliveryAccess]:
        """Atomically record one explicit delivery/download against token limits."""
        now = datetime.now(UTC)
        asset_id = func.coalesce(
            DeliveryAccess.delivery_asset_id, DeliveryAccess.asset_id
        )
        active_asset = exists(
            select(1).where(
                DeliveryAsset.id == asset_id,
                DeliveryAsset.organization_id == DeliveryAccess.organization_id,
                DeliveryAsset.product_id == DeliveryAccess.product_id,
                DeliveryAsset.is_active.is_(True),
            )
        )
        entitled_order = exists(
            select(1).where(
                FunnelOrder.id == DeliveryAccess.order_id,
                FunnelOrder.organization_id == DeliveryAccess.organization_id,
                FunnelOrder.refunded_at.is_(None),
                or_(
                    and_(
                        FunnelOrder.status == "paid",
                        exists(
                            select(1).where(
                                FunnelOrderItem.order_id == FunnelOrder.id,
                                FunnelOrderItem.organization_id
                                == DeliveryAccess.organization_id,
                                FunnelOrderItem.product_id
                                == DeliveryAccess.product_id,
                            )
                        ),
                    ),
                    and_(
                        FunnelOrder.status == "comped",
                        FunnelOrder.subtotal_amount == 0,
                        FunnelOrder.total_amount == 0,
                        FunnelOrder.paid_at.is_(None),
                        exists(
                            select(1).where(
                                FunnelOrderItem.order_id == FunnelOrder.id,
                                FunnelOrderItem.organization_id
                                == DeliveryAccess.organization_id,
                                FunnelOrderItem.product_id
                                == DeliveryAccess.product_id,
                                FunnelOrderItem.unit_amount == 0,
                                FunnelOrderItem.total_amount == 0,
                            )
                        ),
                        exists(
                            select(1).where(
                                LeadMagnet.organization_id
                                == DeliveryAccess.organization_id,
                                LeadMagnet.target_product_id
                                == DeliveryAccess.product_id,
                                LeadMagnet.delivery_asset_id == asset_id,
                                LeadMagnet.status.in_({"published", "active"}),
                            )
                        ),
                    ),
                ),
            )
        )
        conditions = [
            DeliveryAccess.id == access.id,
            DeliveryAccess.access_token_hash == access.access_token_hash,
            DeliveryAccess.organization_id == access.organization_id,
            DeliveryAccess.order_id == access.order_id,
            DeliveryAccess.product_id == access.product_id,
            DeliveryAccess.status == "active",
            or_(DeliveryAccess.expires_at.is_(None), DeliveryAccess.expires_at > now),
            or_(
                DeliveryAccess.max_downloads.is_(None),
                DeliveryAccess.download_count < DeliveryAccess.max_downloads,
            ),
            active_asset,
            entitled_order,
        ]
        result = await self.db.execute(
            update(DeliveryAccess)
            .where(and_(*conditions))
            .values(
                download_count=DeliveryAccess.download_count + 1,
                first_accessed_at=func.coalesce(
                    DeliveryAccess.first_accessed_at, now
                ),
                last_accessed_at=now,
            )
            .returning(DeliveryAccess.id)
            .execution_options(synchronize_session=False)
        )
        access_id = result.scalar_one_or_none()
        if access_id is None:
            return None
        await self.db.commit()
        consumed = await self.db.get(DeliveryAccess, access_id)
        if consumed:
            await self.db.refresh(consumed)
        return consumed

    async def consume_delivery_access_by_token(
        self, raw_token: str
    ) -> Optional[DeliveryAccess]:
        access = await self.get_delivery_access_by_token(raw_token)
        if access is None:
            return None
        return await self.consume_delivery_access(access)

    async def get_file_download(
        self, raw_token: str
    ) -> Optional[Tuple[Path, str]]:
        """Validate a file request and atomically consume one use before streaming."""
        access = await self.get_delivery_access_by_token(raw_token)
        if access is None:
            return None
        order, asset = await self._get_entitled_order_and_asset(access)
        if not order or not asset or asset.asset_type != "file":
            return None
        resolved_path = await self._resolve_asset_file_for_access(
            access, asset, order
        )
        if resolved_path is None:
            return None

        filename = re.sub(r'[\r\n\\/:*?"<>|]+', "_", asset.title).strip(" .")
        filename = filename or "download"
        suffix = Path(resolved_path.name).suffix
        if suffix and not filename.lower().endswith(suffix.lower()):
            filename += suffix
        consumed = await self.consume_delivery_access(access)
        if consumed is None:
            return None
        return resolved_path, filename

    async def record_open(self, access: DeliveryAccess) -> DeliveryAccess:
        """Persist a delivery open against an already validated access token."""
        now = datetime.now(UTC)
        access.open_count = (access.open_count or 0) + 1
        access.first_opened_at = access.first_opened_at or now
        access.last_opened_at = now
        await self.db.commit()
        await self.db.refresh(access)
        return access

    async def grant_delivery_access_for_asset(
        self,
        organization_id: UUID,
        order_id: UUID,
        product_id: UUID,
        delivery_asset_id: UUID,
        *,
        expires_in_days: int = 30,
        max_downloads: int = 10,
        commit: bool = True,
    ) -> Optional[Tuple[DeliveryAccess, str]]:
        """Grant exactly one tenant-scoped asset for a comped lead-magnet order."""
        order = await self.db.scalar(
            select(FunnelOrder).where(
                FunnelOrder.id == order_id,
                FunnelOrder.organization_id == organization_id,
                FunnelOrder.status == "comped",
                FunnelOrder.subtotal_amount == 0,
                FunnelOrder.total_amount == 0,
                FunnelOrder.paid_at.is_(None),
                FunnelOrder.refunded_at.is_(None),
            )
        )
        if order is None:
            return None
        item = await self.db.scalar(
            select(FunnelOrderItem).where(
                FunnelOrderItem.order_id == order_id,
                FunnelOrderItem.organization_id == organization_id,
                FunnelOrderItem.product_id == product_id,
                FunnelOrderItem.unit_amount == 0,
                FunnelOrderItem.total_amount == 0,
            )
        )
        asset = await self.db.scalar(
            select(DeliveryAsset).where(
                DeliveryAsset.id == delivery_asset_id,
                DeliveryAsset.organization_id == organization_id,
                DeliveryAsset.product_id == product_id,
                DeliveryAsset.is_active.is_(True),
            )
        )
        if item is None or asset is None:
            return None

        existing = await self.db.scalar(
            select(DeliveryAccess).where(
                DeliveryAccess.order_id == order_id,
                DeliveryAccess.organization_id == organization_id,
                DeliveryAccess.delivery_asset_id == delivery_asset_id,
            )
        )
        if existing:
            return None

        raw_token = self._generate_token()
        access = DeliveryAccess(
            organization_id=organization_id,
            order_id=order_id,
            order_item_id=item.id,
            product_id=product_id,
            asset_id=asset.id,
            delivery_asset_id=asset.id,
            contact_id=order.contact_id,
            access_token_hash=self._hash_token(raw_token),
            status="active",
            max_downloads=max_downloads,
            expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
            download_count=0,
        )
        self.db.add(access)
        if commit:
            await self.db.commit()
            await self.db.refresh(access)
        else:
            await self.db.flush()
        return access, raw_token

    async def list_order_delivery_accesses(self, organization_id: UUID, order_id: UUID) -> List[DeliveryAccess]:
        stmt = select(DeliveryAccess).where(
            and_(
                DeliveryAccess.order_id == order_id,
                DeliveryAccess.organization_id == organization_id
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _get_asset_for_access(
        self, access: DeliveryAccess
    ) -> Optional[DeliveryAsset]:
        asset_id = access.delivery_asset_id or access.asset_id
        if asset_id is None:
            return None
        return await self.db.scalar(
            select(DeliveryAsset).where(
                DeliveryAsset.id == asset_id,
                DeliveryAsset.organization_id == access.organization_id,
                DeliveryAsset.product_id == access.product_id,
                DeliveryAsset.is_active.is_(True),
            )
        )

    async def _get_entitled_order_and_asset(
        self, access: DeliveryAccess
    ) -> Tuple[Optional[FunnelOrder], Optional[DeliveryAsset]]:
        """Validate tenant-scoped order state and explicit comped entitlement."""
        asset = await self._get_asset_for_access(access)
        if asset is None:
            return None, None
        order = await self.db.scalar(
            select(FunnelOrder).where(
                FunnelOrder.id == access.order_id,
                FunnelOrder.organization_id == access.organization_id,
            )
        )
        if order is None or order.refunded_at is not None:
            return None, None
        if order.status == "paid":
            item = await self.db.scalar(
                select(FunnelOrderItem).where(
                    FunnelOrderItem.order_id == order.id,
                    FunnelOrderItem.organization_id == access.organization_id,
                    FunnelOrderItem.product_id == access.product_id,
                )
            )
            if item is None:
                return None, None
            return order, asset
        if (
            order.status != "comped"
            or order.subtotal_amount != 0
            or order.total_amount != 0
            or order.paid_at is not None
        ):
            return None, None

        item = await self.db.scalar(
            select(FunnelOrderItem).where(
                FunnelOrderItem.order_id == order.id,
                FunnelOrderItem.organization_id == access.organization_id,
                FunnelOrderItem.product_id == access.product_id,
                FunnelOrderItem.unit_amount == 0,
                FunnelOrderItem.total_amount == 0,
            )
        )
        magnet = await self.db.scalar(
            select(LeadMagnet).where(
                LeadMagnet.organization_id == access.organization_id,
                LeadMagnet.target_product_id == access.product_id,
                LeadMagnet.delivery_asset_id == asset.id,
                LeadMagnet.status.in_({"published", "active"}),
            )
        )
        if item is None or magnet is None:
            return None, None
        return order, asset

    async def _resolve_asset_file_for_access(
        self,
        access: DeliveryAccess,
        asset: DeliveryAsset,
        order: Optional[FunnelOrder] = None,
    ) -> Optional[Path]:
        if order is None:
            order, entitled_asset = await self._get_entitled_order_and_asset(access)
            if entitled_asset is None or entitled_asset.id != asset.id:
                return None
        if order is None:
            return None
        if order.status == "comped":
            return self.resolve_lead_magnet_storage_file(asset.storage_path)
        if order.status == "paid":
            return self.resolve_storage_file(asset.storage_path)
        return None

    async def get_delivery_metadata(self, access: DeliveryAccess) -> dict:
        """Return only non-sensitive asset metadata; never reveal the payload."""
        order, asset = await self._get_entitled_order_and_asset(access)
        if order is None or asset is None:
            return {}
        product = await self.db.scalar(
            select(DigitalProduct).where(
                DigitalProduct.id == access.product_id,
                DigitalProduct.organization_id == access.organization_id,
            )
        )
        if product is None:
            return {}
        if asset.asset_type == "file" and await self._resolve_asset_file_for_access(
            access, asset, order
        ) is None:
            return {}
        return {
            "product_name": product.name,
            "asset_title": asset.title,
            "asset_type": asset.asset_type,
            "expires_at": access.expires_at,
            "downloads_remaining": (
                access.max_downloads - access.download_count
                if access.max_downloads is not None
                else None
            ),
        }

    async def get_delivery_payload(self, access: DeliveryAccess) -> dict:
        """Construct a payload for an explicit reveal/consume operation."""
        order, asset = await self._get_entitled_order_and_asset(access)
        if order is None or asset is None:
            return {}
        product = await self.db.scalar(
            select(DigitalProduct).where(
                DigitalProduct.id == asset.product_id,
                DigitalProduct.organization_id == access.organization_id,
                DigitalProduct.id == access.product_id,
            )
        )
        if not product:
            return {}

        payload = {
            "product_name": product.name,
            "asset_title": asset.title,
            "asset_type": asset.asset_type,
            "expires_at": access.expires_at,
            "downloads_remaining": (
                access.max_downloads - access.download_count
                if access.max_downloads is not None
                else None
            ),
        }

        if asset.asset_type in {"text", "private_page", "content"}:
            if asset.content_body is None:
                return {}
            payload["content_body"] = asset.content_body
        elif asset.asset_type == "external_link":
            parsed = urlsplit(asset.external_url or "")
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return {}
            payload["external_url"] = asset.external_url
        elif asset.asset_type == "file":
            if await self._resolve_asset_file_for_access(access, asset, order) is None:
                return {}
        else:
            return {}

        return payload
