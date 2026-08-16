"""Escalation bot — policy denials become 1-click human approvals.

When a policy gate denies a money-moving action (e.g. SUPPLIER_PURCHASE), the
system raises an Approval (PENDING) + Telegram notification instead of just
logging an incident. The CEO approves/rejects through the existing
POST /api/approvals/{id}/decide endpoint; approved actions are replayed
automatically (idempotent). This is the step that makes "100% automation"
safe: humans only touch the denials, never the happy path.
"""
from __future__ import annotations

from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import ApprovalStatus
from ..models import Approval, Order, Product

logger = structlog.get_logger()


async def escalate(db: AsyncSession, object_type: str, object_id, title: str,
                   preview: str, notifier=None) -> Optional[Approval]:
    """Create a PENDING approval (one per object until decided). Returns the
    Approval (or the existing pending one)."""
    existing = await db.scalar(select(Approval).where(
        Approval.object_type == object_type,
        Approval.object_id == object_id,
        Approval.status == ApprovalStatus.PENDING,
    ))
    if existing is not None:
        return existing  # idempotent: one open approval per object
    approval = Approval(object_type=object_type, object_id=object_id,
                        title=title, preview=preview,
                        status=ApprovalStatus.PENDING)
    db.add(approval)
    await db.flush()
    if notifier is not None:
        try:
            await notifier().send_message(
                text=f"APPROVAL NEEDED: {title}\n{preview}\n"
                     f"Decide via POST /api/approvals/{approval.id}/decide")
        except Exception:
            logger.exception("escalation_notify_failed", approval_id=str(approval.id))
    return approval


async def replay_approved(db: AsyncSession, approval: Approval) -> dict:
    """Re-run the approved action by object_type (idempotent by design)."""
    if approval.object_type == "supplier_order":
        order = await db.get(Order, approval.object_id)
        if order is None:
            return {"status": "error", "reason": "order_not_found"}
        product = await db.get(Product, order.product_id)
        if product is None:
            return {"status": "error", "reason": "product_not_found"}
        from ..channels.supplier_pod import SupplierPODAdapter
        so = await SupplierPODAdapter().submit_order(db, order, product)
        await db.commit()
        if so is None:
            return {"status": "denied_again",
                    "reason": "policy still denies — check latest rules"}
        return {"status": "submitted", "supplier_order_id": str(so.id)}
    return {"status": "unsupported", "object_type": approval.object_type}
