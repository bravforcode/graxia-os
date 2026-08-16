"""
scripts/seed_revenue_os_demo.py
Seed Revenue OS with realistic demo data for investor/competition demos.

Creates tables (idempotent) and inserts: products, customers, orders + ledger,
campaigns, approvals (pending for CEO console), incidents, 30-day metrics,
channel connections, affiliates, and leads.

Usage (PowerShell):
    $env:DATABASE_URL="postgresql+asyncpg://graxia:graxia@localhost:5436/graxia_os"
    python scripts/seed_revenue_os_demo.py

Idempotent: skips seeding if products already exist.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

# Ensure repo root on path (script runs from repo root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine

from graxia.database import Base
from graxia.packages.revenue_os import models  # noqa: F401  (register tables)
from graxia.packages.revenue_os.db import DATABASE_URL, get_db_session
from graxia.packages.revenue_os.enums import (
    AffiliateStatus, ApprovalStatus, CampaignStatus, ChannelType,
    IncidentSeverity, LeadStatus, LedgerEntryType, OrderStatus,
    ProductStatus, ProductType,
)

NOW = datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Seed data
# ─────────────────────────────────────────────────────────────────────────────

PRODUCTS = [
    dict(
        name="คู่มือเริ่มต้น E-Commerce อัตโนมัติ",
        slug="ecommerce-automation-guide",
        type=ProductType.LEAD_MAGNET, price_cents=0, currency="THB",
        status=ProductStatus.PUBLISHED,
        promise="คู่มือ 30 หน้า: ระบบอัตโนมัติที่ร้านค้าออนไลน์ไทยใช้จริง",
        target_audience="เจ้าของร้านค้าออนไลน์รายเล็ก-กลาง",
        deliverables="PDF 30 หน้า + Checklist 20 ข้อ",
    ),
    dict(
        name="ระบบ Fulfillment อัตโนมัติ",
        slug="auto-fulfillment",
        type=ProductType.LOW_TICKET, price_cents=99000, currency="THB",
        status=ProductStatus.PUBLISHED,
        promise="ส่งของอัตโนมัติ 100% หลังชำระเงิน — ไม่ต้องแตะมือ",
        target_audience="ร้านค้าที่ขายสินค้าดิจิทัล",
        deliverables="Template + ตั้งค่าให้ 1 ช่องทาง",
    ),
    dict(
        name="Graxia Revenue OS — Standard",
        slug="graxia-revenue-os-standard",
        type=ProductType.CORE, price_cents=490000, currency="THB",
        status=ProductStatus.PUBLISHED,
        promise="ระบบ Revenue OS ครบวงจร: orders, campaigns, approvals, incidents",
        target_audience="SME ที่มีรายได้ 1-10 ล้านบาท/ปี",
        deliverables="ซอฟต์แวร์ + onboarding 2 สัปดาห์",
    ),
    dict(
        name="Graxia Revenue OS — Enterprise",
        slug="graxia-revenue-os-enterprise",
        type=ProductType.CORE, price_cents=1990000, currency="THB",
        status=ProductStatus.PUBLISHED,
        promise="Multi-channel + SLA 99.9% + ผู้ดูแลเฉพาะทีม",
        target_audience="ธุรกิจ 10 ล้านบาท+/ปี",
        deliverables="ซอฟต์แวร์ + onboarding 1 เดือน + SLA",
    ),
    dict(
        name="Consulting: Revenue Audit",
        slug="revenue-audit-consulting",
        type=ProductType.SERVICE, price_cents=2500000, currency="THB",
        status=ProductStatus.PUBLISHED,
        promise="ตรวจสอบ funnel + วางระบบอัตโนมัติให้ภายใน 30 วัน",
        target_audience="ธุรกิจที่ต้องการเร่งรายได้",
        deliverables="Report + Roadmap + ตั้งค่าให้",
    ),
]

CUSTOMERS = [
    ("somchai@example.com", "สมชาย ใจดี"),
    ("pimchanok@example.com", "พิมชนก ศรีสุข"),
    ("anuwat@example.com", "อนุวัฒน์ ทรัพย์เจริญ"),
    ("nattapong@example.com", "ณัฐพงศ์ วงศ์สว่าง"),
    ("siriporn@example.com", "ศิริพร แก้วใส"),
    ("thanawat@example.com", "ธนวัฒน์ รุ่งเรือง"),
    ("kittisak@example.com", "กิตติศักดิ์ บุญมี"),
    ("waranya@example.com", "วรัญญา ตั้งตรง"),
]

# (customer_idx, product_idx, amount_cents, status, days_ago)
ORDERS = [
    (0, 1, 99000, OrderStatus.FULFILLED, 28),
    (1, 2, 490000, OrderStatus.FULFILLED, 25),
    (2, 1, 99000, OrderStatus.FULFILLED, 22),
    (3, 2, 490000, OrderStatus.FULFILLED, 20),
    (4, 1, 99000, OrderStatus.FULFILLED, 18),
    (5, 3, 1990000, OrderStatus.FULFILLED, 15),
    (0, 1, 99000, OrderStatus.FULFILLED, 14),
    (6, 2, 490000, OrderStatus.PAID, 3),
    (7, 1, 99000, OrderStatus.PAID, 2),
    (1, 1, 99000, OrderStatus.PENDING, 0),
    (2, 2, 490000, OrderStatus.REFUNDED, 12),
    (4, 1, 99000, OrderStatus.CANCELLED, 9),
]

CAMPAIGNS = [
    dict(
        name="Launch: Fulfillment อัตโนมัติ", slug="launch-auto-fulfillment",
        status=CampaignStatus.COMPLETED, objective="lead_to_sale",
        target_audience="ร้านค้าดิจิทัล", offer_angle="ส่งของอัตโนมัติ 100%",
        primary_cta="ซื้อเลย", utm_source="facebook", utm_medium="cpc",
        utm_campaign="launch-fulfillment", budget_cents=5000000,
    ),
    dict(
        name="Retarget: Standard OS", slug="retarget-standard-os",
        status=CampaignStatus.ACTIVE, objective="lead_to_sale",
        target_audience="ผู้ดาวน์โหลดคู่มือ", offer_angle="Revenue OS ครบวงจร",
        primary_cta="ดูรายละเอียด", utm_source="tiktok", utm_medium="cpc",
        utm_campaign="retarget-standard", budget_cents=3000000,
    ),
    dict(
        name="Lead Magnet: คู่มือฟรี", slug="lead-magnet-guide",
        status=CampaignStatus.ACTIVE, objective="lead_generation",
        target_audience="เจ้าของร้านค้าออนไลน์", offer_angle="คู่มือฟรี 30 หน้า",
        primary_cta="ดาวน์โหลดฟรี", utm_source="facebook", utm_medium="cpc",
        utm_campaign="lead-magnet", budget_cents=1500000,
    ),
]

APPROVALS = [
    dict(
        object_type="campaign", title="เพิ่มงบแคมเปญ Retarget เป็น 5,000 บาท/วัน",
        preview="Agent เสนอเพิ่มงบ 66% หลัง ROAS 4.2 ติดต่อ 7 วัน",
        requested_by_agent="GrowthAgent", reason="ROAS สูงเกินเป้า 2.1x ติดต่อ 7 วัน",
    ),
    dict(
        object_type="email", title="ส่งอีเมลรีวิวลูกค้า 2,400 ราย",
        preview="อีเมลขอรีวิวหลังซื้อ 7 วัน — คาดได้รีวิว 120-240 รายการ",
        requested_by_agent="SalesAgent", reason="รีวิวน้อย — ส่งผลต่อ conversion",
    ),
    dict(
        object_type="price_change", title="ขึ้นราคา Standard OS 4,900 → 5,900 บาท",
        preview="ทดสอบ A/B 2 สัปดาห์: conversion ลด 3% แต่รายได้/ออเดอร์ +18%",
        requested_by_agent="PricingAgent", reason="ผล A/B สนับสนุนการขึ้นราคา",
    ),
]

INCIDENTS = [
    dict(
        severity=IncidentSeverity.MEDIUM, status="open",
        source_agent="FulfillmentAgent", source="delivery_sla",
        title="ออเดอร์ #ORD-2026-0814-003 ค้าง fulfillment เกิน SLA",
        description="ออเดอร์ Standard OS ค้าง 6 ชม. — ระบบแจ้งเตือนอัตโนมัติแล้ว",
    ),
    dict(
        severity=IncidentSeverity.LOW, status="mitigated",
        source_agent="AdsAgent", source="ads_sync",
        title="Meta Ads sync ล่าช้า 40 นาที",
        description="API rate limit — retry สำเร็จ, ข้อมูลครบถ้วน",
    ),
    dict(
        severity=IncidentSeverity.HIGH, status="resolved",
        source_agent="System", source="checkout",
        title="Stripe webhook ล่าช้า 12 นาที (เหตุการณ์จริง)",
        description="ระบบ retry + idempotency จัดการได้ — ไม่มีออเดอร์สูญหาย",
        resolution_notes="Webhook replay สำเร็จ 100% — ไม่มีผลกระทบลูกค้า",
    ),
]

CHANNELS = [
    dict(channel=ChannelType.SHOPIFY, name="Shopify Store", enabled=True,
         config={"shop_domain": "graxia-demo.myshopify.com"}),
    dict(channel=ChannelType.SHOPEE, name="Shopee Official Store", enabled=True,
         config={"shop_id": "demo-shopee-01"}),
    dict(channel=ChannelType.LAZADA, name="Lazada Official Store", enabled=True,
         config={"shop_id": "demo-lazada-01"}),
    dict(channel=ChannelType.TIKTOK_SHOP, name="TikTok Shop", enabled=True,
         config={"shop_id": "demo-tiktok-01"}),
    dict(channel=ChannelType.FX, name="FX Rates", enabled=True,
         config={"fx_rates": {"USD_THB": 34.5, "EUR_THB": 37.2, "SGD_THB": 25.8}}),
]

AFFILIATES = [
    dict(code="KOL-SME-01", email="kol1@example.com", commission_percent=10.0,
         status=AffiliateStatus.ACTIVE),
    dict(code="KOL-SME-02", email="kol2@example.com", commission_percent=12.0,
         status=AffiliateStatus.ACTIVE),
    dict(code="KOL-SME-03", email="kol3@example.com", commission_percent=8.0,
         status=AffiliateStatus.PAUSED),
]

LEADS = [
    ("lead1@example.com", "ลีด 1", "facebook", LeadStatus.QUALIFIED, 82.0),
    ("lead2@example.com", "ลีด 2", "tiktok", LeadStatus.CONTACTED, 64.0),
    ("lead3@example.com", "ลีด 3", "facebook", LeadStatus.NEW, 45.0),
    ("lead4@example.com", "ลีด 4", "google", LeadStatus.RESPONDED, 71.0),
    ("lead5@example.com", "ลีด 5", "tiktok", LeadStatus.NEW, 38.0),
    ("lead6@example.com", "ลีด 6", "facebook", LeadStatus.QUALIFIED, 88.0),
    ("lead7@example.com", "ลีด 7", "google", LeadStatus.LOST, 22.0),
    ("lead8@example.com", "ลีด 8", "tiktok", LeadStatus.CONTACTED, 57.0),
]


# ─────────────────────────────────────────────────────────────────────────────
# Seeding logic
# ─────────────────────────────────────────────────────────────────────────────

async def _create_tables() -> None:
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


async def _seed() -> None:
    async with get_db_session() as db:
        # Idempotency guard
        existing = await db.scalar(select(func.count()).select_from(models.Product))
        if existing:
            print(f"[seed] products already exist ({existing}) — skipping. "
                  f"Use --force to reseed (not implemented; drop tables first).")
            return

        # Products
        products = [models.Product(**p) for p in PRODUCTS]
        db.add_all(products)
        await db.flush()
        product_by_slug = {p.slug: p for p in products}
        print(f"[seed] products: {len(products)}")

        # Customers
        customers = [
            models.Customer(email=email, name=name,
                            first_purchase_at=NOW - timedelta(days=30),
                            last_purchase_at=NOW - timedelta(days=2),
                            tags=["demo"])
            for email, name in CUSTOMERS
        ]
        db.add_all(customers)
        await db.flush()
        print(f"[seed] customers: {len(customers)}")

        # Orders + ledger
        order_count = 0
        for idx, (c_idx, p_idx, amount, status, days_ago) in enumerate(ORDERS):
            product = products[p_idx]
            customer = customers[c_idx]
            created = NOW - timedelta(days=days_ago)
            order = models.Order(
                platform="stripe",
                platform_order_id=f"pi_demo_{idx:04d}",
                idempotency_key=f"demo:{uuid4()}",
                customer_id=customer.id,
                customer_email=customer.email,
                customer_name=customer.name,
                product_id=product.id,
                amount_cents=amount,
                currency="THB",
                status=status,
                saga_state="completed" if status in (
                    OrderStatus.FULFILLED, OrderStatus.PAID) else status.value,
                stripe_payment_intent=f"pi_demo_{idx:04d}",
                purchased_at=created,
                created_at=created,
            )
            db.add(order)
            await db.flush()
            if status in (OrderStatus.FULFILLED, OrderStatus.PAID):
                db.add(models.LedgerEntry(
                    order_id=order.id, entry_type=LedgerEntryType.CHARGE,
                    amount_cents=amount, currency="THB",
                    description=f"Charge for {product.name}",
                    stripe_balance_transaction_id=f"txn_demo_{idx:04d}",
                    created_at=created,
                ))
            elif status == OrderStatus.REFUNDED:
                db.add(models.LedgerEntry(
                    order_id=order.id, entry_type=LedgerEntryType.REFUND,
                    amount_cents=-amount, currency="THB",
                    description="Refund — ลูกค้าขอยกเลิก",
                    created_at=created,
                ))
            order_count += 1
        print(f"[seed] orders: {order_count}")

        # Campaigns
        campaigns = []
        for c in CAMPAIGNS:
            camp = models.RevenueCampaign(**c)
            camp.product_id = products[1].id if c["slug"] != "lead-magnet-guide" else products[0].id
            db.add(camp)
            campaigns.append(camp)
        await db.flush()
        print(f"[seed] campaigns: {len(campaigns)}")

        # Approvals (pending → CEO console demo)
        for a in APPROVALS:
            db.add(models.Approval(
                object_type=a["object_type"],
                object_id=uuid4(),
                title=a["title"],
                preview=a["preview"],
                status=ApprovalStatus.PENDING,
                requested_by_agent=a["requested_by_agent"],
                reason=a["reason"],
                requested_at=NOW - timedelta(hours=2),
                expires_at=NOW + timedelta(days=2),
            ))
        print(f"[seed] approvals: {len(APPROVALS)} pending")

        # Incidents
        for inc in INCIDENTS:
            db.add(models.IncidentEvent(
                severity=inc["severity"], status=inc["status"],
                source_agent=inc["source_agent"], source=inc["source"],
                title=inc["title"], description=inc["description"],
                resolution_notes=inc.get("resolution_notes"),
                created_at=NOW - timedelta(days=1),
                resolved_at=NOW - timedelta(hours=20) if inc["status"] == "resolved" else None,
            ))
        print(f"[seed] incidents: {len(INCIDENTS)}")

        # 30-day metrics with growth trend (demo: revenue climbing)
        base_visits, base_sales, base_revenue = 120, 1, 99000
        for i in range(30, 0, -1):
            day = date.today() - timedelta(days=i)
            growth = 1 + (30 - i) * 0.03  # +3%/day compounding
            visits = int(base_visits * growth)
            sales = max(1, int(base_sales * growth))
            revenue = int(base_revenue * growth)
            db.add(models.MetricDaily(
                date=day, visits=visits, leads=int(visits * 0.08),
                sales=sales, revenue_cents=revenue,
                content_published=1 if i % 3 == 0 else 0,
                email_sent=int(visits * 0.4),
                conversion_rate=round(sales / visits * 100, 2),
            ))
        print("[seed] metrics: 30 days")

        # Channels
        for ch in CHANNELS:
            db.add(models.ChannelConnection(
                channel=ch["channel"], name=ch["name"],
                enabled=ch["enabled"], config=ch["config"],
                last_sync_at=NOW - timedelta(minutes=5),
            ))
        print(f"[seed] channels: {len(CHANNELS)}")

        # Affiliates
        for af in AFFILIATES:
            db.add(models.Affiliate(**af))
        print(f"[seed] affiliates: {len(AFFILIATES)}")

        # Leads
        for email, name, source, status, score in LEADS:
            db.add(models.Lead(
                email=email, name=name, source=source, status=status,
                score=score, tags=["demo"],
                score_rationale=f"demo score {score}",
                created_at=NOW - timedelta(days=5),
            ))
        print(f"[seed] leads: {len(LEADS)}")

        print("[seed] DONE — demo data ready.")


async def main() -> None:
    print(f"[seed] DATABASE_URL host: {DATABASE_URL.split('@')[-1]}")
    await _create_tables()
    await _seed()


if __name__ == "__main__":
    asyncio.run(main())