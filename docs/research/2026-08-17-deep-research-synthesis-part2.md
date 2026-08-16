# Graxia Revenue OS — Deep Research Synthesis (part 2)

## 2. มาตรฐาน "best-in-class" สำหรับ autonomous commerce (web — evidence)

| มาตรฐาน | แหล่ง | Conf | Graxia ปัจจุบัน |
|---|---|---|---|
| Human control + high-stakes ต้อง human approval | Anthropic framework (Aug 2025) | H | ✅ escalation bot + CEO console |
| Harness concept: instructions + guardrails | Anthropic trustworthy-agents (2026) | H | ✅ policy engine |
| **Approval fatigue จริง: users approve ~93%** → containment (sandbox, least-privilege) ดีกว่า prompt ทุกครั้ง | Anthropic how-we-contain-claude (2026) | H | ⚠️ escalation เยอะไป = fatigue |
| Scoped payment + human approval threshold + **audit trail "decision+inputs+actions"** | Stripe agentic-commerce (2026-04) | H | ⚠️ audit trail ต้อง verify/เสริม |
| **Non-deterministic agents ไม่ควร execute irreversible transactions ตรงๆ** + kill switch + tiered HITL | IMF Note 2026/004 (Apr 2026) | H | ⚠️ ยังไม่มี kill switch ชัดเจน |
| Failure mode จริง: OpenAI Operator ซื้อไข่ $31.43 ไม่ได้รับอนุญาต; Project Vend hallucinate payment account | incidentdatabase.ai, anthropic.com/research/project-vend-1 | H | ⚠️ ต้องมี confirmation ทุก money action |
| Observability: OpenTelemetry = standard; Langfuse/LangSmith บน OTel; ATSC spec (agent turns, HITL review events) | langchain.com, langfuse.com, github.com/agent-telemetry-spec/atsc | H | ❌ revenue_os ไม่มี LLM tracing |
| PDPA: enforced, fine สูงสุด 5M THB, 72h breach notification, cross-border ต้อง safeguard | fosrlaw.com (2025-09) | H | ⚠️ ยังไม่ทำ PDPA |
| PCI DSS 4.0.1: SAQ A ถ้าใช้ Stripe-hosted payment elements (card data ไม่แตะระบบเรา) | pcisecuritystandards.org, stripe.com | H | ✅ Stripe รับผิดชอบ |

## 3. ตลาดไทย (web — evidence)

| ตัวเลข | แหล่ง | Conf |
|---|---|---|
| ETDA: e-Commerce ไทย 2023 = **5.96 ล้านล้านบาท** | springnews/mgronline อ้าง ETDA (2024) | H |
| e-Conomy SEA 2025: GMV ไทย **US$56B**, e-commerce โต **22% สูงสุดอาเซียน**, live sellers 850,000 | blog.google (Nov 2025) | H-M |
| FlowAccount: Standard ฿165/ด. · Pro Business ฿457/ด. (sync Shopee/Lazada/TikTok + Open API) | flowaccount.com/pricing (fetch 2026-08) | H |
| Peak: Basic ฿5,000/ปี · Pro+ ฿12,000/ปี (sync marketplace) · Premium ฿35,000/ปี | peakaccount.com (fetch 2026-08) | H |
| LINE OA: Basic ฿1,280/ด. · Pro ฿1,780/ด. | cresclab blog (2026-01) | M |
| Make: Core $9/ด. · Zapier: Pro $19.99/ด. | make.com, zapier.com (fetch 2026-08) | H |
| VA ไทย: ~฿23,500/ด. (salaryexpert) · e-comm VA $7-15/hr | salaryexpert.com, virtualassistantva.com | M |
| **PromptPay ครอง: 82M+ IDs, ~2,000 ล้านรายการ/ด., มูลค่า ฿4.7T** | techsauce.co (Feb 2026) | H |
| CAC/churn Thai B2B SaaS | — | **no evidence found** |
| FlowAccount + Peak กำลังเพิ่ม AI/MCP connector | pricing pages (fetch 2026-08) | H |

**Inference (M):** SME ไทยจ่ายได้จริง ฿250-1,800/ด./tool → pricing 4,900-19,900/ด. ต้องเป็น mid-market หรือ % ของ revenue uplift / bundled fee กับ ERP/marketplace.

## 4. Roadmap ที่แนะนำ (evidence-based, เรียงตามผลกระทบ)

### P0 — เปิดรับเงิน (blocker ตรง)
1. **สร้าง checkout session endpoint ใน revenue_os_api** (`POST /api/checkout/session` → Stripe Checkout) + test — evidence: blocker #1
2. **Wire live Stripe keys** — โหลด `.env.graxia` หรือตั้งใน deploy env; ลบ test key — evidence: blocker #2
3. **ตัดสินใจ money path**: legacy funnel (Vercel) vs revenue_os — ถ้า legacy คือทางจริง ต้องย้าย revenue_os ไป deploy; ถ้า revenue_os คือทางจริง ต้องสร้าง payment initiation — evidence: blocker #3
4. **Fix production frontend API base URL** (127.0.0.1 → จริง) — evidence: blocker #3

### P1 — ความน่าเชื่อถือ (best-in-class)
5. **Kill switch + irreversible action separation** (IMF) — agent ไม่ execute irreversible ตรงๆ; ต้องผ่าน deterministic layer
6. **Audit trail "decision+inputs+actions"** (Stripe) — verify/เสริม StrategyLog/AuditLog ให้ครบ
7. **Approval fatigue mitigation** — batch/plan approval แทน prompt ทุกรายการ (Anthropic 93%)
8. **PDPA compliance** — privacy policy, consent, breach notification flow (fine 5M THB)
9. **LLM observability** — OTel/Langfuse tracing สำหรับ agent decisions + cost tracking

### P2 — Scale/ทำเงิน
10. **SaaS billing/subscription** — Subscription/Plan tables + Stripe subscription + billing portal
11. **PromptPay billing** — รับ PromptPay QR (ตลาดไทยใช้หลัก)
12. **Pricing strategy** — 4,900-19,900/ด. สูงเกิน SME ไทย; พิจารณา % revenue uplift หรือ tier ใหม่
13. **Sentry + backup จริง** — แทน placeholder
14. **Migrations** — alembic สำหรับ revenue_os schema

### P3 — Competitive
15. **Marketplace credentials จริง** (sandbox → live) — blocker #4
16. **Monitor FlowAccount/Peak AI connectors** — คู่แข่งกำลังขยับ

## 5. Open Questions
- Vercel/Render dashboard มี Stripe keys จริงไหม? (unverified — ต้องเช็ค dashboard)
- ทางเงินจริงคือ legacy funnel หรือ revenue_os? (decision ต้องทำ)
- CAC/churn จริงของ Thai B2B SaaS? (no public data — ต้อง interview founders)
- ตัวเลข ETDA 2024/2025? (หน้า JS ดึงไม่ได้)

## 6. Evidence Quality
- Codebase findings: **high** (อ่านไฟล์ตรง, มี line ref)
- Best-practices: **high** (primary sources: Anthropic/Stripe/IMF)
- Market pricing: **high** (first-party pricing pages, fetch 2026-08)
- Market size: **medium-high** (ETDA survey vs e-Conomy scope ต่างกัน)
- CAC/churn: **none** (no evidence found)

## 7. Recommended Next Steps
1. ตัดสินใจ money path (legacy vs revenue_os) — เร็วสุด, กำหนดทุกอย่าง
2. สร้าง checkout session endpoint + test (P0-1)
3. Wire live keys + fix production URL (P0-2, P0-4)
4. Kill switch + audit trail (P1-5, P1-6)
5. แล้วค่อยทำ billing/PromptPay/pricing (P2)