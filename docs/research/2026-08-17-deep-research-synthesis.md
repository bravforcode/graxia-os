# Graxia Revenue OS — Deep Research Synthesis: "Best-in-class + ทำเงินจริง"

> วันที่: 2026-08-17 · วิธี: 3 subagents ขนาน (web market / web best-practices / codebase gap) + cross-reference
> หลักการ: ทุก claim มีหลักฐาน + confidence (H/M/L) · ไม่มีตัวเลข = "no evidence found" · แยก fact/inference/opinion

## Executive Summary

สถาปัตยกรรมตรงมาตรฐานสากลของ autonomous commerce agents (policy-gated + human-in-the-loop + audit) แต่ **ยังรับเงินจริงไม่ได้** — revenue_os ไม่มี endpoint สร้าง checkout session, Stripe key เป็น test placeholder, deployment จริงคือ legacy funnel ไม่ใช่ revenue_os, marketplace ทั้งหมด sandbox ไม่มี credentials. Pricing 4,900-19,900 THB/เดือน สูงกว่าตลาดไทย 10-40 เท่า (FlowAccount 457 THB/เดือน) → ต้องตัดสินใจ pricing model ก่อน scale.

---

## 1. สิ่งที่ BLOCK การทำเงินจริง (codebase — evidence)

| # | Blocker | หลักฐาน | Severity |
|---|---|---|---|
| 1 | **ไม่มี payment initiation ใน revenue_os** — มีแค่ `POST /stripe-webhook` (receiver), ไม่มี `checkout.sessions.create` ใน `graxia/` (grep 0 hits; มีแค่ column `stripe_payment_link_url` models.py:181) | checkout.py:25-114 | **CRITICAL** |
| 2 | **Stripe key ไม่ใช่ของจริง** — `.env:64-66` = `sk_test_4242424242424242` (test key สาธารณะ); `.env.production` ไม่มี Stripe key; live keys อยู่ใน `.env.graxia` ที่ **ไม่มีโค้ดโหลด** (grep `env.graxia` → 0) | .env, .env.production, .env.graxia | **CRITICAL** |
| 3 | **Deploy จริง = legacy funnel ไม่ใช่ revenue_os** — vercel.json:11-28 rewrite `/api/*` → `api/store_main.py`; revenue_os webhook ไม่ได้ deploy; `.env.production:65-68` frontend ชี้ `http://127.0.0.1:8000/api/v1` (localhost ใน production!) | vercel.json, .env.production | **HIGH** |
| 4 | **Marketplace sandbox-only** — adapters จริง + gating ดี (fails closed) แต่ไม่มี credentials เลย (`.env` ไม่มี SHOPEE/LAZADA/TIKTOK/AMAZON keys) | channels/*.py, .env | **HIGH** |
| 5 | **ไม่มี SaaS billing** — ไม่มี Subscription/Plan/Billing table ใน revenue_os models (86 tablenames, ไม่มี billing); `Entitlement` = per-order ไม่ใช่ tier | models.py | **MEDIUM** |
| 6 | **Ops gaps** — Sentry placeholder (`.env:54`), backup bucket = `replace` (`.env.production:51-58`), revenue_os migration มี 1 ไฟล์ (`0010_enterprise_revenue_os_merge.sql`) | .env, .env.production, graxia/migrations/ | **MEDIUM** |
| 7 | **Test gaps** — ไม่มี test_checkout.py ใน revenue_os tests (54 ไฟล์ แต่ไม่มี checkout/billing) | tests/ | **MEDIUM** |

**Correction (cross-reference):** explorer รายงาน "no .github/workflows" — **ผิด** หลักฐานตรง: `.github/workflows/ci.yml` มีอยู่ + แก้ไข + commit (a1d64de7) ในเซสชันนี้. Explorer ถึง max steps.

**Correction 2:** explorer บอก pricing tiers "unverified" — **ผิด** หลักฐานตรง: `scripts/seed_revenue_os_demo.py` seed 990/4,900/19,900 THB (99000/490000/1990000 cents) เองในเซสชันนี้.