"""Tracking ingestion — record carrier tracking numbers on supplier orders.

Data path only (no carrier API): a provider (supplier webhook/poll, carrier
webhook) hands tracking numbers in; this records them on the SupplierOrder
with an audit trail. Tracking is what later flows into marketplace
push_fulfillment calls.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditLog, SupplierOrder


async def ingest_tracking(db: AsyncSession, supplier_order_id, tracking_number: str,
                          carrier: str = "other") -> bool:
    """Record tracking on a supplier order. Returns True when updated."""
    order = await db.get(SupplierOrder, supplier_order_id)
    if order is None:
        return False
    order.tracking_number = tracking_number
    order.raw = {**(order.raw or {}), "carrier": carrier}
    db.add(AuditLog(
        event_type="supplier.tracking.ingested",
        object_type="supplier_order",
        object_id=order.id,
        message=f"tracking {tracking_number} (carrier={carrier})",
        metadata_={"tracking_number": tracking_number, "carrier": carrier},
    ))
    await db.commit()
    return True
