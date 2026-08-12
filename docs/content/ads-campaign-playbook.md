# แคมเปญโฆษณาพร้อมกด — Ai Factory (ขั้นตอน + งบ + โครงสร้าง)

> ระบบ tracking ลงเว็บแล้ว (Meta Pixel + GA4 + TikTok Pixel + purchase event)
> เหลือแค่: สร้างบัญชีโฆษณา → เอา Pixel ID ไปใส่ Vercel env → เปิดแคมเปญตามนี้

## ขั้นตอน 0: เอา Pixel ID ใส่เว็บ (ครั้งเดียว 5 นาที)

| แพลตฟอร์ม | เอาที่ไหน | env บน Vercel |
|---|---|---|
| Meta Pixel | business.facebook.com → Events Manager → Connect data → Website → สร้าง Pixel | `VITE_META_PIXEL_ID` |
| GA4 | analytics.google.com → Admin → Data Streams → Web → เอา ID (G-XXXX) | `VITE_GA4_ID` |
| TikTok | ads.tiktok.com → Assets → Pixel → สร้าง | `VITE_TIKTOK_PIXEL_ID` |

ตั้ง env → deploy → ตรวจ: เปิดเว็บ → DevTools → console ดู `fbq`/`gtag`/`ttq` โหลด

---

## แคมเปญ 1: Meta (Facebook/Instagram) — เริ่ม ฿300/วัน

**เป้าหมาย: เก็บ email (lead magnet) ก่อน แล้ว retarget ขาย**

| องค์ประกอบ | ค่า |
|---|---|
| วัตถุประสงค์ | Leads (เก็บ email) |
| Ad set 1 — งบ ฿200/วัน | Target: ไทย, อายุ 22-45, Interest: ธุรกิจออนไลน์, ขายของออนไลน์, ChatGPT, AI, คอร์สออนไลน์ |
| Ad set 2 — งบ ฿100/วัน | Target: Retargeting — คนที่ visit เว็บ 30 วัน (ใช้ Pixel อัตโนมัติ) |
| Creative | รูป/คลิป: checklist + ข้อความ "แจกฟรี" (copy พร้อมแล้วใน week1-plan-ads.md) |
| KPI | Cost per lead ≤ ฿15-25 → ดีต่อยอด; > ฿40 → เปลี่ยน creative |

**หลังมี lead ≥ 100: เปิด Ad set ขายสินค้า (฿300/วัน) retarget คนที่ดาวน์โหลด**

## แคมเปญ 2: Google Ads (Search) — เริ่ม ฿200/วัน

**เป้าหมาย: คนที่กำลังหาสินค้าแบบเรา (ซื้อเลย)**

Keyword (ภาษาไทย, แนะนำ exact match ก่อน):
- `ai prompts ไทย`, `พรอมต์ ai`, `prompt ภาษาไทย`
- `เทมเพลต notion`, `notion template ธุรกิจ`
- `คอร์ส ai ไทย`, `เรียน ai ฟรี`, `ใช้ ai ทำงาน`

| องค์ประกอบ | ค่า |
|---|---|
| Campaign type | Search |
| งบ | ฿200/วัน |
| Landing | หน้า /products |
| Ad copy | "50 พรอมต์ AI ภาษาไทย ฿149 — ใช้ทำงานจริงได้ทันที" |
| KPI | CTR ≥ 3%, CPC ≤ ฿5-8, Conv (purchase) ≥ 0.5% |

## แคมเปญ 3: TikTok Ads — เริ่ม ฿300/วัน (หลังมีคลิป 3-5 ตัว)

| องค์ประกอบ | ค่า |
|---|---|
| วัตถุประสงค์ | Website Conversions (purchase) |
| งบ | ฿300/วัน |
| Creative | ใช้คลิปที่ทำใน week 1 (คลิปที่มี engagement ดีสุด) |
| KPI | CPA ≤ ฿80-120 ต่อออเดอร์ (สินค้า ฿149 เริ่มกำไรที่ CPA < ฿120) |

---

## งบรวมที่แนะนำ (ค่อยๆ เพิ่มตามข้อมูล)

| สัปดาห์ | Meta | Google | TikTok | รวม/วัน | รวม/เดือน |
|---|---|---|---|---|---|
| 1-2 | ฿300 | ฿200 | — | ฿500 | ~฿10,500 |
| 3-4 | ฿300 | ฿200 | ฿300 | ฿800 | ~฿16,800 |
| 5+ | ปรับตาม CPA ดีสุด | | | | |

## กฎ 3 ข้อ (ห้ามละเมิด)

1. **อย่าเพิ่มงบก่อนมีข้อมูล 50+ คอนเวอร์ชัน** — ให้อัลกอริทึมเรียนรู้ก่อน
2. **ปิดสิ่งที่แพงทันที** — CPA > 2 เท่าของสินค้าราคาถูกสุด → หยุด ad set นั้น
3. **ดู dashboard จริงทุกสัปดาห์**: visits → leads → checkout → purchase (หน้า /api/v1/funnel/analytics/summary)

## สิ่งที่ต้องทำก่อนเปิด ads (สำคัญ)

- [ ] หน้า /products ตรวจว่าสวย + โหลดไว (เปิดบนมือถือ 4G)
- [ ] ตั้งราคาสินค้าให้มี margin ≥ 70% หลังหัก CPA + Stripe fee (2.9%+฿10)
- [ ] ทดสอบจ่ายจริง 1 ครั้ง (ขั้นตอนก่อนหน้า) — กันลูกค้าติดปัญหาตอนซื้อ
- [ ] เตรียมอีเมลต้อนรับ (post-purchase มีแล้ว ✅ ตรวจให้สวย)
