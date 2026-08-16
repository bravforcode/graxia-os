"""Marketplace sync — inventory reconcile (buffers), price sync (shared path,
FX-aware), fee-aware margin gate, daily FX refresh.

Inventory: local_available = channel_stock - stock_buffer, NEVER negative.
Price: shared DynamicPricingEngine.apply path (24h PriceChangeLock inside);
non-THB product currencies convert ABSOLUTE caps via fx_rates.
Margin: SUPPLIER_PURCHASE gate evaluates (amount - cost - fee) / amount with
per-channel fee_rate from ChannelConnection.config (defaults in constants).
"""
from __future__ import annotations

import os
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import PLATFORM_FEE_RATES
from ..enums import ChannelType, ProductStatus
from ..models import ChannelConnection, ChannelInventory, Product
from ..pricing.dynamic import DynamicPricingEngine

FX_CHANNEL = ChannelType.FX


# ── inventory reconcile ──────────────────────────────────────────────────────

async def inventory_reconcile(db: AsyncSession, adapter=None) -> dict:
    """Compute local available = channel_stock - stock_buffer (never negative).

    adapter (optional): push seam — when a channel adapter is wired, the
    affected products are pushed through adapter.sync_products(db, products).
    """
    rows = (await db.execute(select(ChannelInventory))).scalars().all()
    available_map: dict[str, int] = {}
    changed_products: list[Product] = []
    for inv in rows:
        available = max(0, inv.channel_stock - inv.stock_buffer)
        available_map[f"{inv.channel.value}:{inv.product_id}"] = available
        if available != inv.channel_stock:
            product = await db.get(Product, inv.product_id)
            if product is not None:
                changed_products.append(product)
    pushed = 0
    if adapter is not None and changed_products:
        pushed = await adapter.sync_products(db, changed_products)
    await db.commit()
    return {"rows": len(rows), "changed": len(changed_products), "pushed": pushed,
            "available": available_map}


# ── price sync (shared path, FX-aware) ───────────────────────────────────────

async def _fx_rates(db: AsyncSession) -> dict:
    conn = await db.scalar(select(ChannelConnection).where(ChannelConnection.channel == FX_CHANNEL))
    if conn is None:
        return {}
    return (conn.config or {}).get("fx_rates") or {}


async def price_sync(db: AsyncSession, adapter=None) -> dict:
    """Propose+apply via the shared price path (24h lock inside), then push.

    Products in non-THB currency get fx_rate from the fx channel row so the
    PRICE_CHANGE ABSOLUTE cap converts correctly (PERCENT-only otherwise).
    """
    fx = await _fx_rates(db)
    thb_rates = fx.get("THB") or {}
    applied = skipped = 0
    products = (await db.execute(
        select(Product).where(Product.status == ProductStatus.PUBLISHED))).scalars().all()
    changed_products: list[Product] = []
    for product in products:
        delta = await DynamicPricingEngine.propose(db, product)
        if delta is None:
            continue
        fx_rate = None
        if product.currency != "THB" and product.currency in thb_rates:
            fx_rate = thb_rates[product.currency]
        if await DynamicPricingEngine.apply(db, product, delta, fx_rate=fx_rate):
            applied += 1
            changed_products.append(product)
        else:
            skipped += 1
    pushed = 0
    if adapter is not None and changed_products:
        pushed = await adapter.sync_products(db, changed_products)
    await db.commit()
    return {"applied": applied, "skipped": skipped, "pushed": pushed}


async def sync_listings(db: AsyncSession, http_client=None) -> dict:
    """Push local published products to every connected marketplace channel
    (real listing sync — adapters persist listing ids on ChannelInventory).

    http_client: optional injected httpx client (tests use MockTransport).
    """
    from .amazon import AmazonAdapter
    from .lazada import LazadaAdapter
    from .shopee import ShopeeAdapter
    from .tiktok_shop import TikTokShopAdapter
    listing_adapters = {
        ChannelType.SHOPEE: ShopeeAdapter,
        ChannelType.LAZADA: LazadaAdapter,
        ChannelType.TIKTOK_SHOP: TikTokShopAdapter,
        ChannelType.AMAZON: AmazonAdapter,
    }
    results: dict = {}
    for channel, adapter_cls in listing_adapters.items():
        conn = await db.scalar(
            select(ChannelConnection).where(ChannelConnection.channel == channel))
        if conn is None or not conn.enabled:
            results[channel.value] = {"skipped": True, "reason": "not_connected"}
            continue
        invs = (await db.execute(
            select(ChannelInventory).where(ChannelInventory.channel == channel))).scalars().all()
        products = [await db.get(Product, inv.product_id) for inv in invs]
        products = [p for p in products if p is not None and p.status == ProductStatus.PUBLISHED]
        adapter = adapter_cls(config=conn.config or {}, http_client=http_client)
        pushed = await adapter.sync_products(db, products)
        results[channel.value] = {"products": len(products), "pushed": pushed}
    await db.commit()
    return results


# ── fee-aware margin gate (SUPPLIER_PURCHASE) ────────────────────────────────

async def fee_rate_for(db: AsyncSession, platform: str) -> float:
    """Per-channel fee rate: ChannelConnection.config['fee_rate'] override,
    else PLATFORM_FEE_RATES default; unknown platforms -> 0.0."""
    try:
        channel = ChannelType(platform)
    except ValueError:
        return 0.0
    conn = await db.scalar(select(ChannelConnection).where(ChannelConnection.channel == channel))
    if conn is not None and conn.config.get("fee_rate") is not None:
        return float(conn.config["fee_rate"])
    return float(PLATFORM_FEE_RATES.get(platform, 0.0))


async def margin_after_fee(db: AsyncSession, order, product) -> float:
    """(amount - cost - fee) / amount. Fee = amount * per-channel fee_rate.
    Returns 0.0 when amount is 0/unknown — the gate then denies."""
    amount = order.amount_cents or 0
    if amount <= 0:
        return 0.0
    cost = product.supplier_cost_cents or 0
    fee = amount * await fee_rate_for(db, order.platform)
    return (amount - cost - fee) / amount


# ── daily FX refresh ─────────────────────────────────────────────────────────

async def fx_refresh(db: AsyncSession, http_client: Optional[httpx.AsyncClient] = None) -> int:
    """Fetch THB base rates from FX_SOURCE_URL and store into the global
    ChannelConnection(channel='fx').config['fx_rates'] = {"THB": {...}}."""
    url = os.getenv("FX_SOURCE_URL", "https://open.er-api.com/v6/latest/THB")
    if http_client is not None:
        resp = await http_client.get(url)
    else:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
    resp.raise_for_status()
    rates = (resp.json() or {}).get("rates") or {}
    conn = await db.scalar(select(ChannelConnection).where(ChannelConnection.channel == FX_CHANNEL))
    if conn is None:
        conn = ChannelConnection(channel=FX_CHANNEL, name="fx-rates",
                                 config={"fx_rates": {"THB": rates}})
        db.add(conn)
    else:
        conn.config = {**(conn.config or {}), "fx_rates": {"THB": rates}}
    await db.commit()
    return len(rates)
