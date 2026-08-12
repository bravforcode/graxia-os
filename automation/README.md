# Automation Pipeline — Ai Factory

สร้างคอนเทนต์เอง + (ถ้ามี token) โพสต์เอง + สร้างแคมเปญ ads เอง — รันอัตโนมัติทุกวัน 07:30 ไทย ผ่าน GitHub Actions (ฟรี)

## สถาปัตยกรรม

```
GitHub Actions (ฟรี, cron รายวัน)
  └─ automation/run_daily.py
       ├─ content_generator.py   → สร้างคอนเทนต์ (docs/content/generated/)
       ├─ meta_poster.py --post  → โพสต์ FB Page (ถ้ามี META_PAGE_TOKEN)
       └─ meta_poster.py --ads   → สร้างแคมเปญ ads (PAUSED เสมอ = ไม่เสียเงิน)
```

## ทำงานอะไรบ้าง (ทุกวัน)

| ขั้น | ผล | ต้องมี token ไหม |
|---|---|---|
| สร้างคอนเทนต์ (TikTok script + FB post + บทความ) | ไฟล์ JSON ใน `docs/content/generated/` | ❌ ไม่ (เทมเพลตฟรี) / ✅ ถ้าให้ OPENAI_API_KEY ได้ copy แบบ AI |
| โพสต์ Facebook Page อัตโนมัติ | โพสต์จริงบนเพจ | ✅ META_PAGE_TOKEN |
| สร้างแคมเปญ Meta Ads | campaign + adset + ad (**PAUSED** = ไม่เปลืองเงิน) | ✅ META_AD_ACCOUNT_ID + META_ACCESS_TOKEN |
| Commit คอนเทนต์เข้ารีโพ | commit อัตโนมัติ | ❌ ไม่ |

## ตั้งค่า (ครั้งเดียว ~30 นาที)

### 1. เชื่อม GitHub repo กับ Actions
- repo นี้มี workflow อยู่แล้ว — ไปที่ GitHub → Actions tab → enable

### 2. ใส่ secrets (GitHub → Settings → Secrets and variables → Actions)
| Secret | เอามาจากไหน | จำเป็น? |
|---|---|---|
| `OPENAI_API_KEY` | platform.openai.com | ไม่ (ไม่ใส่ = คอนเทนต์เทมเพลต) |
| `META_PAGE_TOKEN` | business.facebook.com → Page → Settings → Access Token (หรือ Graph Explorer) | ไม่ (ไม่ใส่ = คิวคอนเทนต์ ไม่โพสต์) |
| `META_AD_ACCOUNT_ID` | Ads Manager → Settings → Account ID (`act_...`) | ไม่ (ads dry-run เท่านั้น) |
| `META_ACCESS_TOKEN` | developers.facebook.com → App → Marketing API token (ต้องมี ads_management) | ไม่ |
| `META_PAGE_ID` | หน้าเพจ → About → Page ID | ไม่ |

### 3. ทดสอบ
- GitHub → Actions → workflow "free-pipeline" → **Run workflow** (กดเองได้)
- ตรวจ `docs/content/generated/daily-*.json` ถูก commit

### 4. เปิดให้ auto-post / ads จริง (เมื่อพร้อม)
- **โพสต์อัตโนมัติ**: ใส่ `META_PAGE_TOKEN` → workflow จะโพสต์ FB item แรกทุกวัน
- **ads จริง (เสียเงิน)**: แก้ `--ads` → `--ads --live` ใน run_daily.py แล้วปรับ `daily_budget` + เปิด campaign ใน Ads Manager (ผมแนะนำ: ใช้ dry-run ดูโครงสร้างก่อนเสมอ)

## หมายเหตุสำคัญ
- **ads mode เริ่มต้น = PAUSED เสมอ** — ไม่มีทางเสียเงินโดยไม่ตั้งใจ
- คอนเทนต์ TikTok = คิวให้เอาไปถ่าย (TikTok ยังไม่มี open API ฟรีสำหรับโพสต์อัตโนมัติ — ต้อง Manual)
- Pantip/Line/FB กลุ่ม = manual (ไม่มี API) — ใช้เทมเพลตใน docs/content/
- ไฟล์คอนเทนต์ที่ generate: ตรวจ + แก้ก่อนโพสต์ได้ (commit แล้วแก้ก็ได้)
