# Graxia Revenue OS — Architecture & One-Pager

> สำหรับนักลงทุน/ทีม — ภาพรวมระบบ 1 หน้า + แผนผังสถาปัตยกรรม

---

## One-Pager (30 วินาที)

**Graxia Revenue OS** = ระบบปฏิบัติการรายได้อัตโนมัติสำหรับร้านค้าออนไลน์ SME

- **รับออเดอร์** จากทุกช่องทาง (Stripe, Shopify, Shopee, Lazada, TikTok Shop, Amazon)
- **จัดการเงิน** ด้วย ledger แบบ append-only (ตรวจสอบย้อนหลังได้ 100%)
- **ส่งของอัตโนมัติ** + ติดตาม SLA
- **ทำการตลาด** ตั้ง/ปรับแคมเปญตามนโยบาย (budget caps, ROAS gate)
- **แจ้งเตือน** เหตุการณ์ผ่าน Telegram → CEO อนุมัติจากมือถือ (escalation bot)
- **CEO console** อนุมัติ/ปฏิเสธ 3 คลิก — ไม่มีอะไรเกินวงเงินโดยไม่ได้รับอนุญาต

**ตัวเลข:** 314 tests ผ่าน 100% · 30+ scheduled jobs · 4 queues · policy-gated ทุก action

---

## สถาปัตยกรรม (Mermaid)

```mermaid
flowchart TB
    subgraph Channels["Channels (webhook/HMAC)"]
        STRIPE[Stripe]
        SHOPIFY[Shopify]
        SHOPEE[Shopee]
        LAZADA[Lazada]
        TIKTOK[TikTok Shop]
    end

    subgraph API["Revenue OS API (FastAPI)"]
        ROUTER[API Router /api/*]
        AUTH[Admin API Key + Rate Limit]
        CEO[CEO Console /ceo]
        READY[/api/system/readiness]
        METRICS[/api/system/metrics]
    end

    subgraph CORE["Core Domain (revenue_os)"]
        ORDERS[Orders + Ledger]
        FULFILL[Fulfillment + SLA]
        CAMPAIGN[Campaign Engine]
        APPROVAL[Approval Workflow]
        INCIDENT[Incident + Auto-remediation]
        GROWTH[Growth Engine A/B + Pricing]
        AFFILIATE[Affiliate Program]
    end

    subgraph AGENTS["AI Agents (policy-gated)"]
        SALES[SalesAgent]
        FULFILL_A[FulfillmentAgent]
        GROWTH_A[GrowthAgent]
        PRICING[PricingAgent]
        ADS[AdsAgent]
        INCIDENT_A[IncidentAgent]
    end

    subgraph INFRA["Infrastructure"]
        PG[(PostgreSQL)]
        REDIS[(Redis)]
        CELERY[Celery Worker + Beat]
        TELEGRAM[Telegram Notifier]
        EMAIL[Email (Resend)]
    end

    Channels -->|webhook| ROUTER
    ROUTER --> AUTH
    ROUTER --> CORE
    CORE --> PG
    CELERY -->|scheduled jobs| CORE
    CELERY --> REDIS
    AGENTS -->|actions| CORE
    AGENTS -->|escalate| APPROVAL
    APPROVAL --> CEO
    APPROVAL --> TELEGRAM
    INCIDENT --> TELEGRAM
    CORE --> EMAIL
    READY --> PG
    METRICS -->|Prometheus| INFRA
```

---

## หลักการออกแบบ (ที่นักลงทุนควรรู้)

1. **Idempotency ทุกจุด** — webhook ซ้ำ/ช้า ไม่ทำให้ออเดอร์ซ้ำ (unique constraints + retry)
2. **Ledger append-only** — เงินไม่เคยถูกแก้ ย้อนดูได้ตลอด (audit trail)
3. **Policy-gated autonomy** — agent เสนอได้ แต่ทำได้แค่ในวงเงิน (max/min/allow/deny rules)
4. **Staged autonomy** — OFF → SHADOW → LIMITED → FULL (ไม่เคยข้ามขั้น)
5. **Fail-fast credentials** — production ไม่มี key = ไม่ start (ไม่ silent fail)
6. **Human-in-the-loop** — escalation bot + CEO console = ความไว้วางใจ

---

## Stack

| ชั้น | เทคโนโลยี |
|---|---|
| API | FastAPI + SQLAlchemy (async) + Pydantic |
| Worker | Celery + Redis (4 queues) |
| DB | PostgreSQL 16 (asyncpg) |
| AI | Anthropic Claude (copywriter, agents) |
| Notification | Telegram Bot + Resend (email) |
| Payment | Stripe (webhook HMAC) |
| Deploy | Docker Compose (api/worker/beat/redis/postgres) + CI (GitHub Actions) |
| Observability | /api/system/readiness + Prometheus metrics |

---

## ดูเพิ่มเติม

- `docs/ARCHITECTURE.md` — สถาปัตยกรรมเต็มของ Graxia OS
- `docs/investor/01-pitch-deck.md` — pitch deck
- `docs/investor/05-security-compliance.md` — ความปลอดภัย