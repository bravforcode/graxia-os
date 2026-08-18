# Graxia Revenue OS — 3-Month Organic Revenue Roadmap (Design)

**Date:** 2026-08-19 · **Status:** Approved by founder (brainstorming session)
**Sources:** [deep-research-synthesis](/docs/research/2026-08-17-deep-research-synthesis.md) + [part2](/docs/research/2026-08-17-deep-research-synthesis-part2.md) + [pricing-strategy](/docs/strategy/2026-08-17-pricing-strategy.md)

---

## 1. ภาพรวม + เป้าหมาย

**เป้าหมาย 3 เดือน (organic, งบ 0):**
- รับเงินจริงได้ (Stripe live + funnel เปิด)
- ลูกค้าจ่ายจริง 1–3 ราย (warm leads ก่อน, cold ตาม)
- Recurring mechanics ทำงาน (subscription, dunning, retention)
- Outreach engine อัตโนมัติ (DM/email pipeline ทำงานเอง)

**KPI:** MRR, lead→paid conversion, churn, cost per lead (= 0)

**4 เฟส (สองรางขนาน):**

| เฟส | สัปดาห์ | งาน |
|---|---|---|
| **P0: Money-path readiness** | 1–2 | ปิด blockers รับเงิน: subscription checkout mode, seed tiers ใหม่, Stripe Price IDs, production URL, kill switch |
| **P1: Launch + warm leads** | 1–4 | funnel เปิด, content engine รันรายวัน, outreach warm leads (agents draft + ส่ง), lead tracking |
| **P2: Outreach engine** | 5–8 | สร้าง automation จากสิ่งที่พิสูจน์แล้ว: DM/email pipeline, follow-up, scoring — ต่อเมื่อมีลูกค้า 1–2 ราย validate pitch |
| **P3: Scale + recurring** | 9–12 | referral/affiliate, retention (onboarding, support), % uplift pilot กับ mid-market |

**หลักการออกแบบ:**
- ทุกเฟสมี exit gate — ไม่ผ่าน gate ไม่ข้ามเฟส
- งบ 0 → ใช้ของที่มี: GitHub Actions, meta_poster, Telegram, n8n, Stripe free tier
- Agents ทำ automation, founder ทำ decision (approval flow เดิมคงไว้)

---

## 2. รางเทคนิค — Money-path readiness (P0, สัปดาห์ 1–2)

**สถานะเริ่มต้น:** checkout endpoint มีแล้ว (hardcode `mode="payment"`), live key loading มีแล้ว (`.env.graxia`, code-only approved), subscription billing มีแล้ว (P2-10)

| # | งาน | รายละเอียด |
|---|---|---|
| T1 | **Subscription checkout mode** | `graxia/services/revenue_os_api/routers/checkout.py` ต่อยอด `mode="subscription"` + test |
| T2 | **Seed tiers ใหม่** | Starter ฿499 / Growth ฿1,490 / Scale ฿4,900 / Enterprise % uplift — แทน 990/4,900/19,900 เดิม + `PLANS` config map (`scripts/seed_revenue_os_demo.py`) |
| T3 | **Stripe Price IDs** | สร้างใน Stripe dashboard (founder action) + map plan→price_id (`billing_service.py`) |
| T4 | **Production URL fix** | frontend API base `127.0.0.1` → domain จริง (research blocker #3, `.env.production`) |
| T5 | **Deploy revenue_os** | webhook ต้อง reachable จาก Stripe — เลือก host (Render/Fly/Railway มี config อยู่แล้ว) + ตั้ง webhook endpoint จริง |
| T6 | **Kill switch** | ตัวตัดเงินฉุกเฉิน (IMF best practice) — agent ห้าม execute irreversible ตรงๆ, ต้องผ่าน deterministic layer |
| T7 | **Test suite** | checkout subscription tests + webhook E2E + seed verification |

**Exit gate P0:** ทดสอบจ่ายจริง ฿499 ผ่าน Stripe test mode ครบ flow (checkout → webhook → subscription active → billing portal) + kill switch ทำงาน

**Founder actions:** Stripe dashboard — สร้าง Price IDs, ตั้ง webhook endpoint, ยืนยันบัญชี (ถ้ายังไม่ verified)

**ไม่ทำใน P0** (เลื่อน P2/P3): Sentry จริง, backup จริง, alembic migration เต็มรูปแบบ, PromptPay

---

## 3. ราง GTM — Launch + warm leads (P1, สัปดาห์ 1–4)

**หลักการ: ใช้ของที่มีทั้งหมด, agents เตรียม, founder เป็นคนส่ง (ช่วงนี้) — automation มาใน P2**

| # | งาน | รายละเอียด |
|---|---|---|
| G1 | **Funnel เปิด** | legacy Vercel funnel + tier ใหม่ (subscription products), lead magnet ฿0 + auto-fulfillment ฿990 เดิมคงไว้ |
| G2 | **Content engine รันรายวัน** | GitHub Actions cron 07:30 (มีอยู่แล้ว) — content_generator + meta_poster; theme: e-commerce ops, AI agent สำหรับ SME, case study |
| G3 | **Warm lead outreach** | agents draft DM/email personalized ต่อราย (ใช้ข้อมูลร้าน + content), founder review + ส่ง (LINE/FB Messenger/email) — follow-up วันที่ 3 และ 7 |
| G4 | **Lead tracking** | ใช้ leads router ที่มี: status flow `new → contacted → replied → demo → trial → paid → lost` + campaign_id |
| G5 | **Lead magnet nurture** | คนโหลด guide → auto-email → sequence 3 ฉบับ (agents draft, ส่งผ่านของที่มี) |
| G6 | **Research target list** | agents หา 10–20 ร้านเป้าหมาย (Shopee/Lazada/TikTok sellers) สำหรับ cold outreach ใน P2 |

**Exit gate P1:** funnel รับเงินได้ + content รันทุกวัน + warm leads ≥5 รายติดต่อแล้ว + มี ≥1 demo conversation + lead tracking ทำงาน

**Founder actions:** รายชื่อ warm leads (ชื่อร้าน/ช่องทาง/contact), ส่งข้อความ (หรือ approve draft), META_PAGE_TOKEN ถ้าอยากให้โพสต์อัตโนมัติ

**ไม่ทำใน P1:** DM automation, cold outreach อัตโนมัติ, referral

---

## 4. Outreach engine (P2, สัปดาห์ 5–8)

**Trigger: เริ่มต่อเมื่อ P1 gate ผ่าน (มีลูกค้า 1–2 ราย validate pitch แล้ว)**

**ความจริงของช่องทาง (งบ 0):**

| ช่องทาง | อัตโนมัติได้? | วิธี |
|---|---|---|
| Email | เต็มรูปแบบ | agents draft → auto-send (free tier SMTP/Resend) + follow-up sequence วันที่ 3/7/14 |
| FB/IG/LINE/TikTok DM | กึ่งอัตโนมัติ | ไม่มี free API สำหรับ cold DM → agents draft + queue, founder กดส่ง (หรือ approve batch) |
| FB Page post | มีแล้ว | meta_poster รันต่อ |

| # | งาน | รายละเอียด |
|---|---|---|
| O1 | **Template bank** | เก็บ message variants ที่พิสูจน์แล้วใน P1 (reply rate สูงสุด) → 2–3 variants สำหรับ A/B test |
| O2 | **Email outreach engine** | draft + send + follow-up sequence อัตโนมัติ, rate limit (max ~20/วัน/account), opt-out + PDPA |
| O3 | **DM queue** | agents เตรียม draft ต่อราย → queue ในระบบ → founder approve batch → ส่งเอง (หรือผ่าน n8n ถ้ามี connector) |
| O4 | **Lead scoring** | reply → demo → trial → paid; track conversion ต่อ template/ช่องทาง; ปรับอัตโนมัติ (template ที่แพ้ถูกถอด) |
| O5 | **Cold outreach** | ใช้ research list (G6) 10–20 ร้าน — เริ่ม email ก่อน, DM ตาม |

**Exit gate P2:** engine รันจริง + cold leads ≥10 รายติดต่อ + ≥1 cold → demo + มี data conversion ต่อช่องทาง/template

**Founder actions:** email account สำหรับส่ง, approve batch DM (วันละครั้งก็พอ)

**ไม่ทำใน P2:** ads (งบ 0), PromptPay billing, referral engine

---

## 5. Scale + recurring (P3, สัปดาห์ 9–12)

**เป้าหมาย: เปลี่ยนจาก "มีลูกค้าจ่าย" → "รายได้ recurring ที่ยั่งยืน"**

| # | งาน | รายละเอียด |
|---|---|---|
| R1 | **Onboarding flow** | ลูกค้าใหม่เห็น value ภายใน 24 ชม.: setup wizard (เชื่อม channel → import orders → สร้าง campaign แรก), agents ช่วย configure |
| R2 | **Retention** | support router + Telegram bot (มีอยู่) → ticket flow; dunning: subscription ล้มเหลว → email เตือน + retry (billing มีอยู่แล้ว) |
| R3 | **Referral/affiliate** | เปิด affiliate router: ลูกค้าปัจจุบันแนะนำ → ได้เครดิต/ส่วนลด — ต้นทุน 0, ใช้ network ของลูกค้า |
| R4 | **% uplift pilot** | 1 ราย mid-market จาก warm network — attribution rule: uplift = revenue ใน campaign window vs baseline (orders + campaigns มีอยู่แล้ว) |
| R5 | **PromptPay (optional)** | Stripe รองรับ PromptPay ในไทยอยู่แล้ว — เปิดเมื่อมีลูกค้าขอ (config ไม่ใช่ build ใหม่) |
| R6 | **Churn monitoring** | MRR, churn rate, LTV, ARPU — ลง CEO dashboard (มีอยู่แล้ว) |

**Exit gate P3:** MRR > 0 ติดต่อ 2 เดือน + churn < 10%/เดือน + referral ≥1 ราย + onboarding completion > 80%

**Founder actions:** หา candidate mid-market 1 ราย, ตัดสินใจ % uplift (ตัวเลข), อนุมัติ referral terms

---

## 6. Error handling + Testing + Metrics (ทุกเฟส)

**Error handling (เงิน = fail-closed เสมอ):**
- ทุก money action ผ่าน deterministic layer + human approval (policy engine + approval flow เดิม — คงไว้)
- Kill switch ครอบคลุม: checkout, subscription, refund — ตัดได้ทันที
- Webhook idempotency: Stripe webhook → outbox pattern (มีอยู่แล้ว) — ป้องกัน charge ซ้ำ
- Outreach safety: rate limit (max ~20 email/วัน), opt-out ทุกฉบับ, ไม่มี spam pattern — ปกป้อง account + PDPA
- Retry with backoff: email/outreach ส่งพลาด → retry อัตโนมัติ

**Testing:**
- T7 (P0): checkout subscription + webhook E2E + seed verification — test mode จ่าย ฿499 ครบ flow
- P2: rate-limit tests + template A/B data collection
- Regression: coverage เดิม 73.9% (314+ tests) ต้องไม่ลดลง

**Metrics (วัดทุกเฟส):**
- Funnel: visitors → leads → trials → paid (conversion %)
- Outreach: sent → reply → demo → paid (ต่อช่องทาง/template)
- Revenue: MRR, ARPU, churn, LTV → ลง CEO dashboard

**หลักการรวม: ทุกเฟสต้องมี evidence ก่อนข้าม gate — ไม่มีตัวเลข = ไม่ผ่าน**

---

## 7. Open items / Decisions deferred

- Stripe Price IDs — ต้องสร้างใน dashboard (founder)
- Host สำหรับ revenue_os deploy — เลือก Render/Fly/Railway (มี config ครบ)
- % uplift ตัวเลข — ตัดสินใจตอน P3
- Referral terms — ตัดสินใจตอน P3
- Email account สำหรับ outreach — เตรียมตอน P2