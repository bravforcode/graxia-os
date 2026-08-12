# n8n Automation — Ai Factory

ระบบอัตโนมัติแบบ visual (n8n) รันฟรีบนเครื่องคุณ ทำงานแทน/เสริม GitHub Actions pipeline

## งานที่ n8n ทำ

| Workflow | ทำงาน | ทำอะไร |
|---|---|---|
| `daily-content-automation` | ทุกวัน 07:30 | สร้างคอนเทนต์ (OpenAI) → โพสต์ FB Page → commit GitHub → ส่งอีเมลสรุป |
| `store-monitor` | ทุก 15 นาที | เช็ค /health + เรียก process-due (keep warm + automation) → แจ้งเตือนเมื่อพัง |
| `weekly-digest` | ทุกวันจันทร์ 08:00 | ดึง analytics → ส่งอีเมลสรุปยอดขายให้คุณ |

## วิธีติดตั้ง (ฟรี 100% — รันบน Windows ของคุณ)

### 1. ตรวจ prerequisites (ครั้งเดียว)
```powershell
node --version   # ต้องมี Node 18+ (เครื่องคุณมี Node 24 ✅)
```

### 2. เริ่ม n8n
ดับเบิลคลิก `n8n/start-n8n.bat` (หรือรัน:)
```powershell
cd C:\Users\menum\graxia-os-funnel\n8n
npx --yes n8n@latest
```
→ เปิด browser: **http://localhost:5678** → ตั้ง account ครั้งแรก

### 3. Import workflows (3 ไฟล์ในโฟลเดอร์นี้)
n8n UI → **Workflows** → **⋮** → **Import from File** → เลือก:
- `workflows/daily-content-automation.json`
- `workflows/store-monitor.json`
- `workflows/weekly-digest.json`

### 4. ตั้ง Credentials (คลิกที่โหนดที่มี 🔑)
| Credential | ใช้กับ workflow | ได้จาก |
|---|---|---|
| OpenAI API | daily-content | platform.openai.com (ไม่ใส่ = ยังรันได้แต่คอนเทนต์เทมเพลตน้อยลง) |
| Facebook Graph API | daily-content | developers.facebook.com → App → Page token |
| GitHub (PAT) | daily-content | github.com → Settings → Developer settings → PAT (repo scope) |
| Resend API | ทุก workflow | resend.com (มีแล้ว ✅) |

### 5. เปิด workflow (Activate toggle) → ตรวจ Runs

## หมายเหตุสำคัญ

- **รันเมื่อเครื่องคุณเปิดอยู่** — ปิดเครื่อง = n8n หยุด (GitHub Actions ยังเป็นตัวสำรอง $0 บน cloud อัตโนมัติ)
- **ให้รันตลอด 24 ชม.**: ตั้งให้เปิดพร้อม Windows → Task Scheduler → start-n8n.bat (ดู automation/README)
- TikTok/Pantip/FB กลุ่ม: ยัง manual (ไม่มี API) — ใช้คอนเทนต์ที่ generate
- ads: ใช้ Meta Ads API node เพิ่มเองได้เมื่อมี token (แนะนำ dry-run ก่อน)
- ไฟล์ workflow อยู่ใน `n8n/workflows/` — แก้/เพิ่มใน UI แล้ว Export กลับมา commit ได้
