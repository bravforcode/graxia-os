"""Channel endpoints: Shopify webhook (public, HMAC-gated) + admin status/sync
+ marketplace webhook-triggers (poll-only — payload NEVER imported)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.channels.amazon import trigger_amazon_poll
from ....packages.revenue_os.channels.lazada import trigger_lazada_poll
from ....packages.revenue_os.channels.shopee import trigger_shopee_poll
from ....packages.revenue_os.channels.shopify import ShopifyAdapter, import_shopify_orders
from ....packages.revenue_os.channels.tiktok_shop import trigger_tiktok_poll
from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.enums import ChannelType
from ....packages.revenue_os.models import ChannelConnection
from ..dependencies import require_admin_api_key

# Prefix comes from router.py include (/channels) — declaring one here would
# double it (this was a pre-existing path bug: /channels/channels/...).
router = APIRouter()


@router.post("/shopify/webhook")
async def shopify_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Public Shopify webhook — HMAC verified BEFORE parsing (Risk Audit P2-1)."""
    adapter = ShopifyAdapter()
    if not await adapter.verify_webhook(request):
        raise HTTPException(status_code=401, detail="invalid shopify hmac")
    payload = await request.json()
    topic = request.headers.get("x-shopify-topic", "")
    if topic in ("orders/paid", "orders/create", "orders/updated"):
        session = payload  # order object with id + total_price + customer
        normalized = [{
            "platform_order_id": str(session.get("id")),
            "customer_email": (session.get("customer") or {}).get("email") or "unknown@shopify.local",
            "amount_cents": int(float(session.get("total_price", "0")) * 100),
            "currency": (session.get("currency") or "USD").upper(),
            "product_id": None,  # product mapping needs metafield; imported orders w/o product -> incident
            "status": "paid" if session.get("financial_status") == "paid" else "pending",
            "metadata": {"shopify_id": session.get("id")},
        }]
        imported = await import_shopify_orders(db, normalized)
        return {"status": "ok", "imported": imported}
    return {"status": "ignored", "topic": topic}


@router.post("/shopee/webhook")
async def shopee_webhook(db: AsyncSession = Depends(get_db)) -> dict:
    """Poll-only trigger (risk audit #1): the payload is NEVER read or
    imported — the webhook only wakes the poll, which is the source of truth."""
    return {"status": "ok", **await trigger_shopee_poll(db)}


@router.post("/lazada/webhook")
async def lazada_webhook(db: AsyncSession = Depends(get_db)) -> dict:
    return {"status": "ok", **await trigger_lazada_poll(db)}


@router.post("/tiktok_shop/webhook")
async def tiktok_shop_webhook(db: AsyncSession = Depends(get_db)) -> dict:
    return {"status": "ok", **await trigger_tiktok_poll(db)}


@router.post("/amazon/webhook")
async def amazon_webhook(db: AsyncSession = Depends(get_db)) -> dict:
    return {"status": "ok", **await trigger_amazon_poll(db)}


@router.get("", dependencies=[Depends(require_admin_api_key)])
async def list_channels(db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(ChannelConnection))).scalars().all()
    return {"channels": [
        {"id": str(c.id), "channel": c.channel.value, "name": c.name,
         "enabled": c.enabled, "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None}
        for c in rows
    ]}
