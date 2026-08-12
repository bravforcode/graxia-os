"""
Seed Ai Factory with real starter products via the funnel API.

Usage:
    python scripts/seed_products.py --base-url https://graxia-os-funnel.vercel.app

Reads ADMIN_DEFAULT_EMAIL / ADMIN_DEFAULT_PASSWORD from the environment
(or .env.production via python-dotenv). Uses unique slugs per run so
re-runs never collide.
"""
import argparse
import os
import sys
import uuid

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env.production"))

PRODUCTS = [
    {
        "name": "AI Prompt Pack เริ่มต้น (50 Prompts)",
        "slug_base": "ai-prompt-pack-50",
        "short_description": "50 พรอมต์ AI ใช้ทำงานจริง สำหรับคนไทย",
        "description": "ชุดพรอมต์ ChatGPT/Claude 50 อัน แบ่งหมวด: เขียนคอนเทนต์, ทำงานออฟฟิศ, วางแผนธุรกิจ — พร้อมวิธีปรับใช้จริงทีละขั้น",
        "price_amount": "149.00",
        "currency": "THB",
        "product_type": "prompt_pack",
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
                    "- พรอมต์เขียนบล็อก: \"เขียนบทความ 800 คำ เกี่ยวกับ [หัวข้อ] โครงสร้าง: บทนำ 3 ประเด็นหลัก สรุป พร้อม SEO keyword [คีย์เวิร์ด]\"\n"
                    "- พรอมต์ไอเดียหัวข้อ: \"เสนอ 10 หัวข้อคอนเทนต์เกี่ยวกับ [ธุรกิจ] ที่คนไทยสนใจ พร้อมเหตุผลสั้นๆ ต่อหัวข้อ\"\n\n"
                    "## หมวดที่ 2: ทำงานออฟฟิศ\n"
                    "- พรอมต์สรุปประชุม: \"สรุปการประชุมนี้เป็น bullet points ระบุ: การตัดสินใจ, งานที่ต้องทำ, เจ้าของงาน, deadline\"\n"
                    "- พรอมต์เขียนอีเมล: \"เขียนอีเมล [ประเภท เช่น แจ้งล่าช้า] ถึง [ใคร] เนื้อหา: [ใจความ] น้ำเสียงสุภาพ\"\n"
                    "- พรอมต์วิเคราะห์ไฟล์ข้อมูล: \"วิเคราะห์ข้อมูลชุดนี้ หา insight ที่สำคัญ 3 ข้อ พร้อมตัวเลขสนับสนุน\"\n\n"
                    "## หมวดที่ 3: วางแผนธุรกิจ\n"
                    "- พรอมต์วิเคราะห์คู่แข่ง: \"วิเคราะห์คู่แข่ง [ชื่อ] ในแง่: จุดแข็ง จุดอ่อน ราคา กลยุทธ์ — แนะนำวิธีต่าง\"\n"
                    "- พรอมต์ทำแผนการตลาด: \"ทำแผนการตลาด 30 วัน สำหรับ [ธุรกิจ] งบ [งบ] กลุ่มเป้าหมาย [กลุ่ม]\"\n"
                    "- พรอมต์ตั้งราคา: \"แนะนำโครงสร้างราคา สำหรับ [สินค้า/บริการ] โดยอิงต้นทุน [ต้นทุน] และตลาด [ตลาด]\"\n"
                ),
            }
        ],
    },
    {
        "name": "Notion Template ธุรกิจครบวงจร",
        "slug_base": "notion-business-template",
        "short_description": "ระบบจัดการธุรกิจใน Notion: ลูกค้า, งาน, รายรับ",
        "description": "เทมเพลต Notion สำหรับฟรีแลนซ์/SME: CRM ลูกค้า, ติดตามงาน, รายรับ-รายจ่าย, เป้าหมายรายเดือน — พร้อมคู่มือติดตั้ง",
        "price_amount": "299.00",
        "currency": "THB",
        "product_type": "template",
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
                    "- เป้าหมาย: ตั้งเป้ารายเดือน + เช็คความคืบหน้า\n\n"
                    "## เคล็ดลับ\n"
                    "- ใช้ปุ่ม + เพื่อเพิ่มลูกค้า/งานใหม่ได้ทันที\n"
                    "- เปิด Calendar view สำหรับงานที่มี deadline\n"
                    "- Export รายงานรายเดือนจากตารางรายรับ-รายจ่าย\n"
                ),
            }
        ],
    },
    {
        "name": "คอร์ส AI สำหรับธุรกิจ: เริ่มต้นจนใช้งานจริง",
        "slug_base": "ai-business-course",
        "short_description": "เรียนรู้ใช้ AI ในธุรกิจ 5 บทเรียน พร้อมตัวอย่างจริง",
        "description": "คอร์สสอนใช้ ChatGPT/Claude ทำงานธุรกิจจริง: เขียนคอนเทนต์, ตอบลูกค้า, วิเคราะห์ข้อมูล, วางแผนการตลาด — 5 บทเรียน + แบบฝึกหัด + ตัวอย่างผลลัพธ์",
        "price_amount": "499.00",
        "currency": "THB",
        "product_type": "course",
        "assets": [
            {
                "asset_type": "content",
                "title": "บทเรียนที่ 1: พื้นฐานการใช้งาน AI อย่างมืออาชีพ",
                "content_body": (
                    "# คอร์ส AI สำหรับธุรกิจ — บทเรียนที่ 1\n\n"
                    "## สิ่งที่จะได้จากบทเรียนนี้\n"
                    "- เข้าใจว่า AI ช่วยธุรกิจตรงไหนได้จริง\n"
                    "- รู้จักคำศัพท์พื้นฐาน (prompt, context, token)\n"
                    "- ตั้งค่าและเริ่มใช้ ChatGPT/Claude อย่างถูกวิธี\n\n"
                    "## หลักการเขียน Prompt ที่ดี\n"
                    "1. **บอกบทบาท** — \"คุณคือนักการตลาดที่เชี่ยวชาญ SME ไทย\"\n"
                    "2. **ให้บริบท** — \"ธุรกิจของฉันคือร้านกาแฟ ย่านสุขุมวิท ลูกค้าส่วนใหญ่เป็นพนักงานออฟฟิศ\"\n"
                    "3. **ระบุรูปแบบผลลัพธ์** — \"ตอบเป็น bullet points 5 ข้อ ภาษาไทย กระชับ\"\n"
                    "4. **ยกตัวอย่าง** — \"แบบนี้: ...\"\n\n"
                    "## แบบฝึกหัด\n"
                    "เขียน prompt แนะนำร้านกาแฟของคุณให้ ChatGPT แล้วปรับตามหลักการ 4 ข้อด้านบน สังเกตความต่างของคำตอบ\n"
                ),
            },
            {
                "asset_type": "content",
                "title": "บทเรียนที่ 2-5 (สรุปเนื้อหา)",
                "content_body": (
                    "# บทเรียนที่ 2-5\n\n"
                    "## บทที่ 2: เขียนคอนเทนต์และโฆษณาด้วย AI\n"
                    "สูตร: บทบาท + กลุ่มเป้าหมาย + ข้อความที่อยากสื่อ + น้ำเสียง + CTA\n\n"
                    "## บทที่ 3: ตอบลูกค้าและบริการด้วย AI\n"
                    "สร้าง FAQ chatbot, ตอบรีวิว, เขียนตอบแชทลูกค้าในน้ำเสียงแบรนด์\n\n"
                    "## บทที่ 4: วิเคราะห์ข้อมูลธุรกิจด้วย AI\n"
                    "อัปโหลดไฟล์ยอดขาย ให้ AI หา insight, จุดอ่อน, โอกาส\n\n"
                    "## บทที่ 5: วางแผนการตลาด 30 วัน\n"
                    "จากงบประมาณและเป้าหมาย → แผนรายสัปดาห์ พร้อม KPI\n\n"
                    "> เนื้อหาเต็มทั้ง 5 บทเรียนจะส่งให้ในอีเมลถัดไป (ไฟล์ PDF + วิดีโอ)\n"
                ),
            },
        ],
    },
]

LEAD_MAGNETS = [
    {
        "name": "Checklist เปิดร้านออนไลน์ 30 วัน (ฟรี)",
        "slug_base": "checklist-open-online-store",
        "promise": "ดาวน์โหลดฟรี: Checklist เปิดร้านออนไลน์ครบ 30 วัน สำหรับมือใหม่",
        "target_product_slug": "ai-prompt-pack-50",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://graxia-os-funnel.vercel.app")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    email = os.environ.get("ADMIN_DEFAULT_EMAIL", os.environ.get("ADMIN_EMAIL", "admin@graxia.store"))
    password = os.environ.get("ADMIN_DEFAULT_PASSWORD", os.environ.get("ADMIN_PASSWORD", ""))

    with httpx.Client(base_url=base, timeout=60, follow_redirects=True) as c:
        r = c.post("/api/v1/auth/login", json={"email": email, "password": password})
        if r.status_code != 200:
            print(f"Login failed ({r.status_code}): {r.text[:300]}")
            return 1
        token = r.json()["access_token"]
        csrf = c.cookies.get("csrf_token", "")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": csrf,
            "Cookie": f"csrf_token={csrf}",
        }
        print(f"Logged in as {email} (csrf len={len(csrf)})")

        created = 0
        for p in PRODUCTS:
            body = {
                "name": p["name"],
                "slug": f"{p['slug_base']}-{uuid.uuid4().hex[:6]}",
                "short_description": p["short_description"],
                "description": p["description"],
                "price_amount": p["price_amount"],
                "currency": p["currency"],
                "product_type": p["product_type"],
            }
            r = c.post("/api/v1/funnel/products", json=body, headers=headers)
            if r.status_code not in (200, 201):
                print(f"Create failed ({r.status_code}): {r.text[:300]}")
                continue
            product = r.json()
            pid = product["id"]
            for asset in p.get("assets", []):
                ar = c.post(f"/api/v1/funnel/products/{pid}/assets", json=asset, headers=headers)
                if ar.status_code not in (200, 201):
                    print(f"  asset failed ({ar.status_code}): {ar.text[:200]}")
            pr = c.post(f"/api/v1/funnel/products/{pid}/publish", headers=headers)
            ok = pr.status_code == 200
            print(f"[{'OK' if ok else 'PUBLISH FAILED'}] {p['name']} ฿{p['price_amount']} (id={pid})")
            created += 1

        # Lead magnet (free checklist → email capture → upsell)
        for lm in LEAD_MAGNETS:
            target = None
            r = c.get("/api/v1/funnel/products", headers=headers)
            if r.status_code == 200:
                for prod in r.json():
                    if prod.get("slug", "").startswith(lm["target_product_slug"]):
                        target = prod["id"]
                        break
            body = {
                "name": lm["name"],
                "slug": f"{lm['slug_base']}-{uuid.uuid4().hex[:6]}",
                "promise": lm["promise"],
                "target_product_id": target,
            }
            r = c.post("/api/v1/funnel/lead-magnets", json=body, headers=headers)
            if r.status_code in (200, 201):
                lm_id = r.json()["id"]
                pr = c.put(f"/api/v1/funnel/lead-magnets/{lm_id}", json={"status": "published"}, headers=headers)
                print(f"[{'OK' if pr.status_code == 200 else 'FAIL'}] Lead magnet: {lm['name']} (published={pr.status_code})")
            else:
                print(f"[FAIL] Lead magnet create ({r.status_code}): {r.text[:200]}")

        print(f"Done. Created {created}/{len(PRODUCTS)} products + {len(LEAD_MAGNETS)} lead magnet.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
