"""
Seed Ai Factory with starter products via the funnel API.

Usage:
    python scripts/seed_products.py --base-url https://graxia-backend.onrender.com

Env vars:
    ADMIN_EMAIL / ADMIN_PASSWORD  — admin login (seeded admin user)
    or ADMIN_TOKEN                — existing JWT (skips login)
"""
import argparse
import json
import os
import sys

import httpx

PRODUCTS = [
    {
        "name": "AI Prompt Pack เริ่มต้น (50 Prompts)",
        "slug": "ai-prompt-pack-50",
        "short_description": "50 พรอมต์ AI ใช้ทำงานจริง สำหรับคนไทย",
        "description": "ชุดพรอมต์ ChatGPT/Claude 50 อัน แบ่งหมวด: เขียนคอนเทนต์, ทำงานออฟฟิศ, วางแผนธุรกิจ — พร้อมวิธีปรับใช้",
        "price_amount": "149.00",
        "currency": "THB",
        "product_type": "prompt_pack",
        "stripe_price_id": os.environ.get("SEED_STRIPE_PRICE_ID", ""),
        "assets": [
            {
                "asset_type": "content",
                "title": "AI Prompt Pack v1 — เนื้อหาครบชุด",
                "content_body": (
                    "# AI Prompt Pack เริ่มต้น\n\n"
                    "## วิธีใช้\n"
                    "1. คัดลอกพรอมต์ที่ต้องการ\n"
                    "2. วางใน ChatGPT / Claude\n"
                    "3. เปลี่ยน [ตัวแปร] ให้ตรงกับงานของคุณ\n\n"
                    "## หมวดที่ 1: เขียนคอนเทนต์\n"
                    "- พรอมต์เขียนโพสต์โซเชียล: \"เขียนโพสต์ Facebook เกี่ยวกับ [หัวข้อ] ในน้ำเสียง [น้ำเสียง] ความยาว 100 คำ พร้อม Call-to-Action\"\n"
                    "- พรอมต์เขียนบล็อก: \"เขียนบทความ 800 คำ เกี่ยวกับ [หัวข้อ] โครงสร้าง: บทนำ 3 ประเด็นหลัก สรุป พร้อม SEO keyword [คีย์เวิร์ด]\"\n\n"
                    "## หมวดที่ 2: ทำงานออฟฟิศ\n"
                    "- พรอมต์สรุปประชุม: \"สรุปการประชุมนี้เป็น bullet points ระบุ: การตัดสินใจ, งานที่ต้องทำ, เจ้าของงาน, deadline\"\n"
                    "- พรอมต์เขียนอีเมล: \"เขียนอีเมล [ประเภท เช่น แจ้งล่าช้า] ถึง [ใคร] เนื้อหา: [ใจความ] น้ำเสียงสุภาพ\"\n\n"
                    "## หมวดที่ 3: วางแผนธุรกิจ\n"
                    "- พรอมต์วิเคราะห์คู่แข่ง: \"วิเคราะห์คู่แข่ง [ชื่อ] ในแง่: จุดแข็ง จุดอ่อน ราคา กลยุทธ์ — แนะนำวิธีต่าง\"\n"
                    "- พรอมต์ทำแผนการตลาด: \"ทำแผนการตลาด 30 วัน สำหรับ [ธุรกิจ] งบ [งบ] กลุ่มเป้าหมาย [กลุ่ม]\"\n"
                ),
            }
        ],
    },
    {
        "name": "Notion Template ธุรกิจครบวงจร",
        "slug": "notion-business-template",
        "short_description": "ระบบจัดการธุรกิจใน Notion: ลูกค้า, งาน, รายรับ",
        "description": "เทมเพลต Notion สำหรับฟรีแลนซ์/SME: CRM ลูกค้า, ติดตามงาน, รายรับ-รายจ่าย, เป้าหมายรายเดือน",
        "price_amount": "299.00",
        "currency": "THB",
        "product_type": "template",
        "stripe_price_id": os.environ.get("SEED_STRIPE_PRICE_ID_2", ""),
        "assets": [
            {
                "asset_type": "content",
                "title": "Notion Template — วิธีติดตั้ง",
                "content_body": (
                    "# Notion Template ธุรกิจครบวงจร\n\n"
                    "## วิธีติดตั้ง\n"
                    "1. กด Duplicate template (ลิงก์จะส่งในอีเมลถัดไป)\n"
                    "2. ตั้งชื่อ workspace ของคุณ\n"
                    "3. เริ่มใช้งานหน้า Dashboard\n\n"
                    "## โครงสร้าง\n"
                    "- Dashboard: ภาพรวมรายรับ งานค้าง ลูกค้าใหม่\n"
                    "- ลูกค้า (CRM): ฐานข้อมูลลูกค้า + สถานะ\n"
                    "- งาน: Kanban ติดตามงานแต่ละชิ้น\n"
                    "- รายรับ-รายจ่าย: ตารางบันทึกอัตโนมัติ\n"
                ),
            }
        ],
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    token = os.environ.get("ADMIN_TOKEN", "")
    if not token:
        email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
        password = os.environ.get("ADMIN_PASSWORD", "")
        r = httpx.post(f"{base}/api/v1/auth/login", json={"email": email, "password": password})
        if r.status_code != 200:
            print(f"Login failed ({r.status_code}): {r.text}")
            return 1
        token = r.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    created = 0
    for p in PRODUCTS:
        body = {k: v for k, v in p.items() if k != "assets"}
        if not body.get("stripe_price_id"):
            body.pop("stripe_price_id", None)
            print(f"[SKIP price_id] {body['name']} — ยังไม่มี stripe_price_id (สร้างสินค้าใน Stripe แล้วใส่ SEED_STRIPE_PRICE_ID)")
        r = httpx.post(f"{base}/api/v1/funnel/products", json=body, headers=headers)
        if r.status_code not in (200, 201):
            print(f"Create failed ({r.status_code}): {r.text}")
            continue
        product = r.json()
        pid = product["id"]
        for asset in p.get("assets", []):
            ar = httpx.post(f"{base}/api/v1/funnel/products/{pid}/assets", json=asset, headers=headers)
            if ar.status_code not in (200, 201):
                print(f"  asset failed ({ar.status_code}): {ar.text}")
        pr = httpx.post(f"{base}/api/v1/funnel/products/{pid}/publish", headers=headers)
        print(f"[{'OK' if pr.status_code == 200 else 'PUBLISH FAILED'}] {product['name']} (id={pid}) status={pr.status_code}")
        created += 1

    print(f"Done. Created {created}/{len(PRODUCTS)} products.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
