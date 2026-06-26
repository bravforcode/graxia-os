# 🗺️ MOC — Pattern Integration (External Repos → Graxia)

> **Purpose**: Hub สำหรับเอกสารทั้งหมดที่เกี่ยวกับการ integrate patterns จาก 5 external repos เข้า Graxia quant_os
> **Maintainer**: bridge agent
> **Last updated**: 2026-06-26

---

## 📚 Core Documents

| Document | Description | Status |
|----------|-------------|--------|
| [[integration_mega_plan]] | แผนละเอียด 7 สัปดาห์ พร้อม acceptance criteria, risk register, rollback plan | Draft |
| [[integration_plan]] | High-level plan 5 patterns + roadmap | Draft |
| [[repo_audit_report]] | Audit 27 repos + เลือก 5 ตัวหลัก | Done |

---

## 🧩 Patterns Being Integrated

| Pattern | Source Repo | Target Module | Phase |
|---------|-------------|---------------|-------|
| Strategy API helpers | jesse-ai/jesse | `strategies/base.py` | A |
| Kelly + VaR risk | kvrancic/algorithmic-trading-bot | `risk/` | B |
| Numba + Arrow performance | cyclux/tradeforce | `backtest/` | B/C |
| Multi-agent ensemble | tauricresearch/tradingagents | `core/agents/` | C |
| Event-driven design | letianzj/quanttrader | `core/events.py`, `core/event_bus.py` | A/B |

---

## 🗂️ Related State Files

- [[bridge_state]] — สถานะล่าสุดของ bridge agent
- [[bridge_handoff]] — handoff notes ระหว่าง agents
- [[bridge_fixes_2026-06-26]] — bug fixes ที่เกี่ยวข้อง

---

## ✅ Next Actions

1. Approve [[integration_mega_plan]]
2. Begin Phase A — Foundation (A1: Strategy helpers)
3. Run baseline benchmark ก่อนเริ่ม implement

---

## 🏷️ Tags

#integration #patterns #jesse #kvrancic #tradeforce #tradingagents #quanttrader #quant_os #bridge
