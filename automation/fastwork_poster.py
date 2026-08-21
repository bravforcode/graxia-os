"""
FastWork service poster — post dev services (products) to FastWork automatically.

Reverse-engineered from the public web app (api.fastwork.co / gateway.fastwork.co).
Flow: generate drafts (template, no AI key needed) -> human approves -> script posts + submits.

Never posts anything without an explicit --post of an APPROVED draft.

Auth (no password needed — use the JWT from your browser):
    FASTWORK_JWT        — paste from browser: fastwork.co -> DevTools Console ->
                          document.cookie.split('; ').find(c => c.startsWith('accessToken='))
                          (run --jwt-help)  [JWT is in a COOKIE named accessToken, not localStorage]
    FASTWORK_EMAIL + FASTWORK_PASSWORD — fallback login (ถ้าหา JWT ไม่ได้)

Usage:
    python automation/fastwork_poster.py --generate          # create drafts (template, $0)
    python automation/fastwork_poster.py --list              # show drafts + status
    python automation/fastwork_poster.py --approve <id>      # mark a draft approved
    python automation/fastwork_poster.py --reject <id>       # mark a draft rejected
    python automation/fastwork_poster.py --jwt-help          # how to get FASTWORK_JWT
    python automation/fastwork_poster.py --verify            # test auth + fetch my services
    python automation/fastwork_poster.py --categories        # list dev categories
    python automation/fastwork_poster.py --post <id> [--dry-run]
    python automation/fastwork_poster.py --post --all-approved [--dry-run]
"""
import argparse
import json
import os
import sys
import uuid
from datetime import date, datetime

# Windows console defaults to cp1252 — force UTF-8 so Thai output doesn't crash
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DRAFTS_DIR = ROOT / "docs" / "content" / "fastwork"
DRAFTS_FILE = DRAFTS_DIR / "drafts.json"

HOST = "https://fastwork.co"
API = "https://api.fastwork.co"
GATEWAY = "https://gateway.fastwork.co"

TIMEOUT = 30

# Which subcategory slug each project targets (fastwork.co/<slug>).
# Override per draft with --category <slug>.
PROJECT_CATEGORY = {
    "Business Dashboard Automation": "data-engineering",
    "Testlyn — Hospital Management System": "web-development",
    "Plexta — Auction Web Platform": "web-development",
    "API & System Integration": "it-solution-and-support",
}


# ── auth ────────────────────────────────────────────────────────────────────
def get_jwt() -> str:
    """JWT from FASTWORK_JWT env, else login with email/password. Raises on failure."""
    jwt = os.environ.get("FASTWORK_JWT", "").strip()
    if jwt:
        return jwt
    email = os.environ.get("FASTWORK_EMAIL", "")
    password = os.environ.get("FASTWORK_PASSWORD", "")
    if not email or not password:
        raise SystemExit(
            "no auth: set FASTWORK_JWT (run --jwt-help) or FASTWORK_EMAIL + FASTWORK_PASSWORD"
        )
    r = httpx.post(f"{HOST}/api/login", json={"email": email, "password": password}, timeout=TIMEOUT)
    data = r.json()
    if not data.get("isLoggedIn") or not data.get("userJwt"):
        raise SystemExit(f"login failed: {data}")
    return data["userJwt"]


def headers(jwt: str) -> dict:
    return {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json", "fw-locale": "th"}


# ── categories (GraphQL via gateway) ────────────────────────────────────────
CATEGORIES_QUERY = """
query {
  categories {
    id
    title
    slug
    subcategory_groups {
      id
      title
      subcategories {
        active
        id
        category_id
        slug
        title
        minimum_price
      }
    }
  }
}
"""


def get_subcategories(jwt: str) -> list[dict]:
    """All active subcategories: [{id, slug, title, category_id, minimum_price}]."""
    r = httpx.post(f"{GATEWAY}/graphql", headers=headers(jwt), json={"query": CATEGORIES_QUERY}, timeout=TIMEOUT)
    data = r.json()
    if "errors" in data:
        raise SystemExit(f"categories query failed: {data['errors']}")
    cats = data.get("data", {}).get("categories", [])
    out = []
    for c in cats:
        for g in c.get("subcategory_groups", []):
            for s in g.get("subcategories", []):
                if s.get("active"):
                    out.append(s)
    return out


def find_subcategory(jwt: str, slug: str) -> dict:
    subs = get_subcategories(jwt)
    for s in subs:
        if s["slug"] == slug:
            return s
    raise SystemExit(f"subcategory slug not found: {slug} (available: {', '.join(s['slug'] for s in subs[:20])}...)")


# ── product API ─────────────────────────────────────────────────────────────
def get_my_services(jwt: str) -> dict:
    r = httpx.post(f"{API}/api/v4/product.getMyServices", headers=headers(jwt), json={}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def create_product(jwt: str, payload: dict) -> dict:
    """POST /api/v4/products — returns parsed response (product id on success)."""
    r = httpx.post(f"{API}/api/v4/products", headers=headers(jwt), json=payload, timeout=TIMEOUT)
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {"raw_status": r.status_code, "raw_body": r.text}


def update_packages(jwt: str, product_id: str, packages: list[dict]) -> dict:
    r = httpx.put(f"{API}/api/v4/products/{product_id}/packages", headers=headers(jwt), json={"packages": packages}, timeout=TIMEOUT)
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {"raw_status": r.status_code, "raw_body": r.text}


def submit_product(jwt: str, product_id: str) -> dict:
    r = httpx.put(f"{API}/api/v4/products/{product_id}/submit", headers=headers(jwt), timeout=TIMEOUT)
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {"raw_status": r.status_code, "raw_body": r.text}


# ── draft store ─────────────────────────────────────────────────────────────
def load_drafts() -> list[dict]:
    if not DRAFTS_FILE.exists():
        return []
    return json.loads(DRAFTS_FILE.read_text(encoding="utf-8")).get("drafts", [])


def save_drafts(drafts: list[dict]) -> None:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    DRAFTS_FILE.write_text(json.dumps({"version": 1, "drafts": drafts}, ensure_ascii=False, indent=2), encoding="utf-8")


def find_draft(drafts: list[dict], draft_id: str) -> dict:
    for d in drafts:
        if d["id"] == draft_id:
            return d
    raise SystemExit(f"draft not found: {draft_id} (use --list)")


# ── content generation (template only — no AI key needed) ──────────────────
def load_projects() -> list[dict]:
    import yaml

    p = ROOT / "identity" / "projects.yaml"
    if not p.exists():
        raise SystemExit(f"{p} not found")
    return yaml.safe_load(p.read_text(encoding="utf-8")).get("projects", [])


# Thai service copy per project (title <= 60 chars, description ~150-250 chars).
SERVICE_COPY = {
    "Business Dashboard Automation": {
        "title": "ทำระบบ Dashboard ธุรกิจอัตโนมัติ รายงานแบบ Real-time",
        "description": (
            "รับทำระบบ BI Dashboard อัตโนมัติสำหรับธุรกิจ SME และสตาร์ทอัพ "
            "รวบรวมข้อมูลจากหลายแหล่ง (Excel, ฐานข้อมูล, API) เข้าสู่ระบบเดียว "
            "ประมวลผล ETL อัตโนมัติ และแสดงผลเป็นกราฟแดชบอร์ดแบบเรียลไทม์ "
            "แทนการทำรายงานด้วยมือที่ช้าและผิดพลาด — เจ้าของธุรกิจเห็นตัวเลข "
            "ยอดขาย สต็อก และผลประกอบการได้ทันทีโดยไม่ต้องจ้างทีม data "
            "เทคโนโลยี: Python, ETL, PostgreSQL, React, Power BI"
        ),
    },
    "Testlyn — Hospital Management System": {
        "title": "ทำระบบบริหารโรงพยาบาล/คลินิก ครบวงจร (HMS)",
        "description": (
            "รับพัฒนาระบบบริหารโรงพยาบาลและคลินิกแบบครบวงจร "
            "จัดการเวชระเบียนผู้ป่วย การนัดหมาย พนักงาน และขั้นตอนการทำงาน "
            "ทั้งหมดในระบบเดียว แทนที่กระดาษและสเปรดชีต "
            "ลดความผิดพลาดของข้อมูล เพิ่มความเร็วในการให้บริการ "
            "ออกแบบมาเพื่อคลินิกและโรงพยาบาลขนาดเล็กในไทยโดยเฉพาะ "
            "เทคโนโลยี: React, Node.js, PostgreSQL, Docker, REST API"
        ),
    },
    "Plexta — Auction Web Platform": {
        "title": "ทำเว็บประมูลออนไลน์ Real-time ครบวงจร",
        "description": (
            "รับพัฒนาเว็บแพลตฟอร์มประมูลออนไลน์แบบเรียลไทม์ "
            "ระบบประมูลสด (live bidding) การลงขายสินค้า การจัดการผู้ซื้อ-ผู้ขาย "
            "ยืนยันตัวตน และการชำระเงิน ครบในแพลตฟอร์มเดียว "
            "เหมาะสำหรับธุรกิจประมูลและตลาดซื้อขายของมือสองออนไลน์ "
            "ไม่มีค่าธรรมเนียมบุคคลที่สาม ประสบการณ์ใช้งานลื่นไหลทั้งมือถือและคอม "
            "เทคโนโลยี: React, Node.js, PostgreSQL, WebSockets, TailwindCSS"
        ),
    },
    "API & System Integration": {
        "title": "เชื่อมต่อ API ระหว่างระบบธุรกิจอัตโนมัติ",
        "description": (
            "รับทำระบบเชื่อมต่อ API ระหว่างระบบธุรกิจที่แยกกันอยู่ "
            "ให้ข้อมูลไหลเวียนอัตโนมัติโดยไม่ต้องคีย์มือซ้ำ "
            "เช่น ระบบขาย-สต็อก-บัญชี-CRM เชื่อมถึงกัน "
            "ลดงาน manual ลดความผิดพลาด และรองรับการขยายระบบในอนาคต "
            "ออกแบบสถาปัตยกรรมให้ยืดหยุ่น พร้อมเอกสารและโค้ดสะอาด "
            "เทคโนโลยี: Node.js, Python, REST API, PostgreSQL, MongoDB"
        ),
    },
}

PACKAGES = [
    {"name": "Basic", "price": 14900, "delivery_days": 7,
     "description": "เริ่มต้น — งานตาม scope หลัก พร้อมแก้ไข 1 รอบ"},
    {"name": "Standard", "price": 29900, "delivery_days": 14,
     "description": "ยอดนิยม — ครบทุกฟีเจอร์ + แก้ไข 2 รอบ + ทดสอบระบบ"},
    {"name": "Premium", "price": 59900, "delivery_days": 30,
     "description": "เต็มรูปแบบ — ฟีเจอร์ทั้งหมด + deploy + สอนใช้งาน + support 30 วัน"},
]


def gen_templated() -> list[dict]:
    """Deterministic Thai template drafts — works with $0, no API key."""
    now = datetime.now().isoformat(timespec="seconds")
    drafts = []
    for proj in load_projects():
        slug = PROJECT_CATEGORY.get(proj["name"], "web-development")
        copy = SERVICE_COPY.get(proj["name"], {})
        drafts.append(
            {
                "id": f"fw_{uuid.uuid4().hex[:6]}",
                "project": proj["name"],
                "category_slug": slug,
                "title": copy.get("title", proj["tagline"]),
                "description": copy.get("description", proj["description"].strip()),
                "packages": [dict(p) for p in PACKAGES],
                "status": "pending",
                "created_at": now,
                "posted_at": None,
                "product_id": None,
                "subcategory_id": None,
            }
        )
    return drafts


# ── posting ─────────────────────────────────────────────────────────────────
def post_draft(jwt: str, draft: dict, dry_run: bool = False) -> dict:
    """Create product + packages + submit. Returns result dict."""
    sub = find_subcategory(jwt, draft["category_slug"])
    payload = {
        "category_id": sub["category_id"],
        "subcategory_id": sub["id"],
        "title": draft["title"],
        "description": draft["description"],
        "attribute_value_ids": [],
        "tag_ids": [],
    }
    if dry_run:
        print(f"[dry-run] would POST {API}/api/v4/products with {json.dumps(payload, ensure_ascii=False)}")
        return {"ok": True, "dry_run": True, "subcategory": sub}
    created = create_product(jwt, payload)
    product_id = str(created.get("id") or created.get("data", {}).get("id") or "")
    if not product_id:
        return {"ok": False, "step": "create", "response": created}
    pkgs = update_packages(jwt, product_id, draft["packages"])
    submitted = submit_product(jwt, product_id)
    return {"ok": True, "product_id": product_id, "packages_response": pkgs, "submit_response": submitted}


def cmd_generate() -> int:
    drafts = load_drafts()
    new_drafts = gen_templated()
    drafts.extend(new_drafts)
    save_drafts(drafts)
    print(f"Generated {len(new_drafts)} drafts -> {DRAFTS_FILE.relative_to(ROOT)}")
    for d in new_drafts:
        print(f"  [{d['id']}] {d['title']} ({d['category_slug']}) — {d['status']}")
    return 0


def cmd_list() -> int:
    drafts = load_drafts()
    if not drafts:
        print("no drafts yet — run --generate first")
        return 0
    for d in drafts:
        print(f"  [{d['id']}] {d['status']:8s} {d['title']} (category={d['category_slug']})")
    return 0


def cmd_set_status(draft_id: str, status: str) -> int:
    drafts = load_drafts()
    d = find_draft(drafts, draft_id)
    d["status"] = status
    save_drafts(drafts)
    print(f"{draft_id} -> {status}")
    return 0


def cmd_verify() -> int:
    jwt = get_jwt()
    svc = get_my_services(jwt)
    print(f"auth OK. getMyServices -> {json.dumps(svc, ensure_ascii=False)[:500]}")
    return 0


def cmd_categories() -> int:
    jwt = get_jwt()
    subs = get_subcategories(jwt)
    print(f"{len(subs)} subcategories:")
    for s in subs:
        print(f"  {s['slug']:40s} id={s['id']} cat={s['category_id']} min={s.get('minimum_price')}")
    return 0


def cmd_jwt_help() -> int:
    print("วิธีง่ายสุด (1 คลิก, ไม่ต้องเปิด DevTools):")
    print("  1) เปิดไฟล์ automation/fastwork_bookmarklet.html (ดับเบิ้ลคลิก)")
    print("  2) ลากปุ่มดำ '⚡ คัดลอก FastWork JWT' ไปไว้บน Bookmarks Bar (Ctrl+Shift+B ถ้าไม่เห็น bar)")
    print("  3) เปิด https://fastwork.co แล้ว login ให้สำเร็จ")
    print("  4) คลิก bookmark ที่ลากไว้ -> จะคัดลอก JWT ให้อัตโนมัติ (popup)")
    print("  5) วาง JWT ลง .env.local:  python automation/fastwork_poster.py --paste")
    print("     (หรือวางเอง: FASTWORK_JWT=eyJ... ใน .env.local)")
    print("")
    print("วิธีสำรอง (ไม่มี bookmark bar): F12 -> Application -> Cookies -> https://fastwork.co -> accessToken")
    return 0


def cmd_paste() -> int:
    env_path = ROOT / ".env.local"
    raw = input("วาง JWT (eyJ...): ").strip().strip('"').strip("'")
    if not raw or not raw.startswith("eyJ"):
        print("ดูไม่เหมือน JWT (ควรขึ้นต้น eyJ...) — ยกเลิก")
        return 1
    # upsert FASTWORK_JWT in .env.local
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith("FASTWORK_JWT="):
            lines[i] = f"FASTWORK_JWT={raw}"
            found = True
            break
    if not found:
        lines.append(f"FASTWORK_JWT={raw}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"บันทึกแล้ว -> {env_path} (len={len(raw)})")
    print("ทดสอบ: python automation/fastwork_poster.py --verify")
    return 0


def cmd_post(draft_id: str | None, all_approved: bool, dry_run: bool) -> int:
    jwt = get_jwt()
    drafts = load_drafts()
    targets = []
    if all_approved:
        targets = [d for d in drafts if d["status"] == "approved"]
        if not targets:
            print("no approved drafts — approve first (--approve <id>)")
            return 1
    else:
        if not draft_id:
            print("need --post <id> or --post --all-approved")
            return 1
        targets = [find_draft(drafts, draft_id)]

    for d in targets:
        if d["status"] not in ("approved",):
            print(f"skip {d['id']}: status={d['status']} (must be approved)")
            continue
        print(f"posting {d['id']}: {d['title']}")
        result = post_draft(jwt, d, dry_run=dry_run)
        print(f"  -> {json.dumps(result, ensure_ascii=False)[:400]}")
        if result.get("ok"):
            d["status"] = "posted"
            d["posted_at"] = datetime.now().isoformat(timespec="seconds")
            d["product_id"] = result.get("product_id")
            d["subcategory_id"] = str(result.get("subcategory", {}).get("id", "")) if not dry_run else None
            save_drafts(drafts)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="FastWork service poster")
    parser.add_argument("--generate", action="store_true", help="create drafts from templates (no AI needed)")
    parser.add_argument("--list", action="store_true", help="list drafts")
    parser.add_argument("--approve", metavar="ID", help="mark draft approved")
    parser.add_argument("--reject", metavar="ID", help="mark draft rejected")
    parser.add_argument("--verify", action="store_true", help="verify JWT + fetch my services (test credentials)")
    parser.add_argument("--categories", action="store_true", help="list dev subcategories (auth required)")
    parser.add_argument("--jwt-help", action="store_true", help="how to get FASTWORK_JWT from browser")
    parser.add_argument("--paste", action="store_true", help="paste JWT and save to .env.local")
    parser.add_argument("--post", metavar="ID", help="post one approved draft")
    parser.add_argument("--all-approved", action="store_true", help="post all approved drafts")
    parser.add_argument("--dry-run", action="store_true", help="print payloads without calling create API")
    args = parser.parse_args()

    if args.generate:
        return cmd_generate()
    if args.list:
        return cmd_list()
    if args.approve:
        return cmd_set_status(args.approve, "approved")
    if args.reject:
        return cmd_set_status(args.reject, "rejected")
    if args.verify:
        return cmd_verify()
    if args.categories:
        return cmd_categories()
    if args.jwt_help:
        return cmd_jwt_help()
    if args.paste:
        return cmd_paste()
    if args.post or args.all_approved:
        return cmd_post(args.post, args.all_approved, args.dry_run)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
