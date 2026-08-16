"""POD/dropship supplier adapter — policy-gated order submission (idempotent),
status webhooks (HMAC), polling."""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy_engine import PolicyEngine
from ..enums import ActionType, IncidentSeverity, SupplierStatus
from ..models import IncidentEvent, Product, SupplierOrder
from .marketplace_sync import margin_after_fee


class SupplierPODAdapter:
    """Printful-style supplier. client must implement:
    async submit(order_id, idempotency_key) -> dict; async get_status(ref) -> dict."""

    def __init__(self, client=None):
        self.client = client or DefaultSupplierClient()

    async def submit_order(self, db: AsyncSession, order, product: Product) -> Optional[SupplierOrder]:
        """Policy-gated, idempotent submission. Returns SupplierOrder or None if denied."""
        existing = await db.scalar(
            select(SupplierOrder).where(SupplierOrder.order_id == order.id)
        )
        if existing is not None:
            return existing  # already submitted (idempotent)

        cost = product.supplier_cost_cents or 0
        if cost <= 0:
            # unknown cost -> policy cannot protect the order; escalate
            db.add(IncidentEvent(
                title=f"Supplier order blocked (unknown cost): {order.id}",
                description="supplier_cost_cents is 0/None — set it before auto-ordering",
                severity=IncidentSeverity.MEDIUM,
                affected_order_id=order.id,
            ))
            await db.flush()
            return None
        margin_percent = (await margin_after_fee(db, order, product)) * 100
        decision = await PolicyEngine.check(
            db, ActionType.SUPPLIER_PURCHASE,
            {
                "value": margin_percent,
                "value_cents": cost,
                "order_id": str(order.id),
                "currency": order.currency,
            },
        )
        if not decision.allow:
            db.add(IncidentEvent(
                title=f"Supplier order denied by policy: {order.id}",
                description=decision.reason,
                severity=IncidentSeverity.MEDIUM,
                affected_order_id=order.id,
            ))
            # Escalation bot: denial becomes a 1-click approval (money-moving
            # actions get a human decision instead of a silent drop).
            from ..approvals.escalation import escalate
            from graxia.services.telegram_notifier import UnifiedTelegramNotifier
            await escalate(db, "supplier_order", order.id,
                           title=f"Supplier order needs approval: order {order.id}",
                           preview=f"{decision.reason} — order {order.id} "
                                   f"{order.amount_cents}{order.currency}",
                           notifier=UnifiedTelegramNotifier)
            await db.flush()
            return None

        so = SupplierOrder(
            order_id=order.id,
            supplier=product.supplier or "unknown",
            idempotency_key=f"po-{order.id}",
            status=SupplierStatus.SUBMITTED,
        )
        db.add(so)
        await db.flush()
        try:
            result = await self.client.submit(order_id=str(order.id), idempotency_key=so.idempotency_key)
            so.supplier_order_ref = result.get("id")
            so.raw = result
            so.status = SupplierStatus.SUBMITTED
        except Exception:
            # network/timeout: leave SUBMITTED without ref — poll job retries,
            # duplicate submission impossible via unique idempotency_key
            pass
        await db.commit()
        return so

    async def poll(self, db: AsyncSession) -> dict:
        """Poll suppliers for status changes on submitted orders with refs."""
        updated = 0
        rows = (await db.execute(
            select(SupplierOrder).where(
                SupplierOrder.status.notin_([SupplierStatus.DELIVERED, SupplierStatus.FAILED]),
            )
        )).scalars().all()
        for so in rows:
            if so.supplier_order_ref is None:
                # SUBMITTED without ref (previous attempt failed): retry submission.
                # Idempotency key makes retries safe.
                from ..models import Order as OrderModel
                order = await db.get(OrderModel, so.order_id)
                product = await db.get(Product, order.product_id) if order else None
                if order is None or product is None:
                    continue
                try:
                    result = await self.client.submit(order_id=str(order.id), idempotency_key=so.idempotency_key)
                    so.supplier_order_ref = result.get("id")
                    so.raw = result
                    updated += 1
                except Exception:
                    continue  # retry next tick
                continue
            try:
                status = await self.client.get_status(so.supplier_order_ref)
                new_status = status.get("status", "").lower()
                if new_status in ("in_production", "production"):
                    so.status = SupplierStatus.IN_PRODUCTION
                elif new_status in ("shipped", "fulfilled"):
                    so.status = SupplierStatus.SHIPPED
                    so.tracking_number = status.get("tracking_number")
                elif new_status in ("delivered", "complete"):
                    so.status = SupplierStatus.DELIVERED
                    so.tracking_number = status.get("tracking_number")
                elif new_status in ("failed", "cancelled"):
                    so.status = SupplierStatus.FAILED
                    db.add(IncidentEvent(
                        title=f"Supplier order failed: {so.id}",
                        description=f"supplier status={new_status}",
                        severity=IncidentSeverity.MEDIUM,
                    ))
                else:
                    continue
                updated += 1
            except Exception:
                continue
        await db.commit()
        return {"updated": updated}


class DefaultSupplierClient:
    """Real supplier HTTP client (Printful-style). Reads SUPPLIER_API_URL + SUPPLIER_API_KEY.
    Kept thin: tests inject fakes; production integration verified in runbook."""

    async def submit(self, order_id: str, idempotency_key: str) -> dict:
        import httpx
        url = os.getenv("SUPPLIER_API_URL", "")
        key = os.getenv("SUPPLIER_API_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPPLIER_API_URL / SUPPLIER_API_KEY not configured")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{url}/orders", json={"external_order_id": order_id},
                headers={"Authorization": f"Bearer {key}", "Idempotency-Key": idempotency_key},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_status(self, ref: str) -> dict:
        import httpx
        url = os.getenv("SUPPLIER_API_URL", "")
        key = os.getenv("SUPPLIER_API_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPPLIER_API_URL / SUPPLIER_API_KEY not configured")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{url}/orders/{ref}", headers={"Authorization": f"Bearer {key}"}
            )
            resp.raise_for_status()
            return resp.json()


def parse_status_webhook(payload: bytes, signature: str) -> Optional[dict]:
    """Verify HMAC (SUPPLIER_WEBHOOK_SECRET) and return parsed fields, or None."""
    import json
    secret = os.getenv("SUPPLIER_WEBHOOK_SECRET", "")
    if not secret:
        return None
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        return None
    try:
        data = json.loads(payload)
    except Exception:
        return None
    return {"order_ref": data.get("id") or data.get("order_ref"),
            "status": data.get("status", ""),
            "tracking": data.get("tracking_number") or data.get("tracking")}
