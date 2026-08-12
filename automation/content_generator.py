"""
Content Generator — creates ready-to-publish content every run.

Works with $0 (template-based) or with OPENAI_API_KEY for full AI copy.
Output goes to docs/content/generated/ and is committed by CI.
"""
import argparse
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "content" / "generated"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PRODUCTS = [
    {"name": "AI Prompt Pack เริ่มต้น (50 Prompts)", "price": "149", "slug": "ai-prompt-pack", "url": "https://graxia-os-funnel.vercel.app"},
    {"name": "Notion Template ธุรกิจครบวงจร", "price": "299", "slug": "notion-business-template", "url": "https://graxia-os-funnel.vercel.app"},
    {"name": "คอร์ส AI สำหรับธุรกิจ", "price": "499", "slug": "ai-business-course", "url": "https://graxia-os-funnel.vercel.app"},
]

# ── Template-based copy (works without any API key) ────────────────────────
TIKTOK_SCRIPTS = [
    "พรอมต์ AI ที่ใช้ทุกวัน — \"คุณคือนักการตลาด SME ไทย...\" วิธีนี้ทำให้เขียนคอนเทนต์เร็ว 5 เท่า มีอีก 49 พรอมต์ในโปรไฟล์ #AI #promptไทย",
    "ฟรีแลนซ์ใช้ AI ทำงานเร็ว 2 เท่า — 3 งานที่ AI ทำแทนได้: เขียนแคปชัน สรุปไฟล์ ตอบลูกค้า #freelancerไทย #AI",
    "3 ความผิดพลาดของการใช้ ChatGPT — ไม่บอกบทบาท ไม่ให้บริบท ไม่ระบุรูปแบบ แก้ได้ใน 1 นาที #ChatGPT #AIไทย",
]

FB_POSTS = [
    "ให้ความรู้: AI ไม่ได้แย่งงาน — คนที่ใช้ AI เป็นจะรับงานได้มากขึ้น ตัวอย่างพรอมต์ที่ใช้จริงในคอมเมนต์ครับ",
    "แจกฟรี! Checklist เปิดร้านออนไลน์ 30 วัน — ดาวน์โหลดได้ที่ลิงก์ (ไม่มีค่าใช้จ่าย) #ธุรกิจออนไลน์",
    "โพลล์: คุณใช้ AI ทำงานประจำวันไหม? 👍 ใช้ทุกวัน / ❤️ ใช้บางงาน / 😮 สนใจ / 🔥 ยังไม่ได้ผล",
]

BLOG_OUTLINES = [
    "บทความ: วิธีใช้ AI เขียนคอนเทนต์ให้คนไทยอ่าน — โครงสร้าง: บทนำ / 4 เทคนิค / ตัวอย่างพรอมต์ / สรุป + CTA",
    "บทความ: AI กับ SME ไทย — 3 งานที่ AI ช่วยได้จริง (การตลาด, บริการลูกค้า, เอกสาร)",
]


def gen_templated() -> dict:
    """Template-based content — deterministic, $0."""
    today = date.today().isoformat()
    items = []
    for i, t in enumerate(TIKTOK_SCRIPTS, 1):
        items.append({"channel": "tiktok", "title": f"TikTok script {i}", "body": t, "status": "queue", "date": today})
    for i, p in enumerate(FB_POSTS, 1):
        items.append({"channel": "facebook", "title": f"FB post {i}", "body": p, "status": "queue", "date": today})
    for i, b in enumerate(BLOG_OUTLINES, 1):
        items.append({"channel": "blog", "title": f"Blog outline {i}", "body": b, "status": "draft", "date": today})
    return {"generated_at": today, "items": items}


def gen_with_ai() -> dict:
    """Full AI copy (requires OPENAI_API_KEY). Falls back to templates on any failure."""
    import httpx

    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        return gen_templated()
    prompts = [
        "เขียนสคริปต์ TikTok 30-45 วินาที ภาษาไทย โปรโมทสินค้าดิจิทัล 'AI Prompt Pack' ราคา 149 บาท เนื้อหา: สาธิต 1 พรอมต์ที่ใช้ทำงานจริง ลงท้าย CTA ให้คลิกลิงก์ในโปรไฟล์",
        "เขียนโพสต์ Facebook ให้ความรู้เรื่องการใช้ AI ทำงาน สำหรับกลุ่มฟรีแลนซ์ไทย 150-200 คำ ภาษาไทยเป็นกันเอง ไม่ใช่โฆษณาตรงๆ",
        "เขียนบทความบล็อกภาษาไทย 600-800 คำ หัวข้อ 'AI สำหรับ SME ไทย: เริ่มใช้จริงใน 7 วัน' พร้อม SEO keyword และ CTA ท้ายบทความ",
    ]
    items = []
    for i, prompt in enumerate(prompts, 1):
        try:
            r = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "max_tokens": 900},
                timeout=60,
            )
            data = r.json()
            body = data["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            print(f"AI item {i} failed ({exc}) — using template fallback")
            return gen_templated()
        items.append({"channel": "ai", "title": f"AI item {i}", "body": body, "status": "queue", "date": date.today().isoformat()})
    return {"generated_at": date.today().isoformat(), "items": items}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai", action="store_true", help="use OpenAI if key present")
    args = parser.parse_args()

    data = gen_with_ai() if args.ai else gen_templated()
    filename = f"daily-{date.today().isoformat()}-{uuid.uuid4().hex[:6]}.json"
    out = OUT_DIR / filename
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {len(data['items'])} items -> {out.relative_to(ROOT)}")
    for item in data["items"]:
        print(f"  [{item['channel']}] {item['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
