# Change Control

**Date:** 2026-07-01
**Author:** coordinator-agent
**Status:** ACTIVE

---

## Change Request Reference

This document is the formal phase change request for all strategy, data, execution, risk, and model changes described in the GRAXIA-TSM Unified Mega Remediation Plan. It supersedes narrower XAUUSD-only and TSM-only plans. All modifications to the trading system during this remediation cycle must be tracked against this ticket.

---

## Scope

One unified trading system merging GRAXIA-OS data/signal/runtime layers with TSM portfolio/backtest realism. The scope includes:

- **GRAXIA-OS:** data ingestion, feature store, signal generation, SMC detectors, model training, risk controls, OMS, monitoring, and evidence.
- **TSM:** multi-asset portfolio realism, backtest/live parity, regime exposure, cost realism, and paper-trade strategy parity.
- **Shared runtime:** one canonical path from data -> features -> signal -> risk -> OMS -> broker adapter -> ledger -> monitoring.

---

## Priority Order

1. **Security first** — remove account/system takeover paths, secret exposure, injection, and replay vectors.
2. **Completeness** — ensure all critical issues from the 82-item audit are addressed with evidence.
3. **Long-term maintainability** — ops, CI/CD, runbooks, and code quality for sustained operation.

---

## Linked Plan

- **Plan file:** `Meta/GRAXIA_TSM_UNIFIED_MEGA_REMEDIATION_PLAN_2026-07-01.md`
- **Plan scope:** 10 waves (0-9), 50+ tasks, covering security, data truth, risk/OMS safety, backtest/paper parity, ML/feature rebuild, realistic portfolio validation, ops, paper trade campaign, and live readiness review.

---

## Locked Experiment Outputs

The following experiment outputs are locked and must NOT be overwritten during this remediation cycle:

- XAUUSD_D1 raw historical data files.
- Any existing backtest result reports under `reports/`.
- Any existing shadow run or dry-run outputs under `shadow_results/`.
- Existing audit reports and readiness JSON files.

**No live trading is authorized until ALL of the following are proven with evidence artifacts:**

1. Security — no plaintext secrets, rotation complete, auth on all endpoints, replay protection, SQL injection closed.
2. OMS-risk coupling — OMS cannot bypass pre-trade risk check, contract snapshot binding enforced.
3. Kill switch — closes/hedges open exposure by policy, persists across restart, emits audit events.
4. Data truth — canonical datasets with manifests, contamination quarantined, multi-asset overlap proven, macro joins point-in-time.
5. Realistic costs — unified cost model, XAUUSD 72 bps stress tested, swap/rollover addressed.
6. Statistical validation — purged+embargo CV, early stopping, PBO/deflated Sharpe, multiple testing correction.

---

## Wave Summary

| Wave | Name | Gate Requirement |
|-----:|------|------------------|
| 0 | Freeze and Evidence Baseline | Baseline report — current truth reproducible |
| 1 | Security Closure | Security gate — no plaintext secrets, auth on all endpoints, replay protection, SQL injection fixed, backup/restore tested |
| 2 | Data Truth | Data gate — canonical datasets with manifests, contamination removed, overlap truth, feature NaNs below threshold, macro PIT or excluded |
| 3 | Risk and OMS Safety | Safety gate — OMS cannot bypass risk, kill switch handles open positions, circuit breaker integrated, contract snapshot binds sizing, BTC/ETH routing correct |
| 4 | Backtest/Paper Parity | Parity gate — shared return/fill/cost/missing-bar semantics, paper bot proves actual asset weights, account equity source consistent |
| 5 | ML/Feature Rebuild | Model gate — features_v3 documented, purge+embargo proven, early stopping active, multiple testing correction, registry captures hashes |
| 6 | Realistic Portfolio Validation | Edge gate — net edge positive after costs (or ARCHIVE_NO_EDGE), mean-reversion regime risk controlled, portfolio PBO/DSR pass |
| 7 | Ops and Maintainability | Ops gate — CI/CD, Prometheus/Grafana, correlation IDs, trainer healthcheck, DB migrations, runbook handoff |
| 8 | Paper Trade Campaign | Paper verdict — preflight hard blockers, 24hr dry run, 7-day demo campaign with full order lifecycle evidence |
| 9 | Live Readiness Review | Final verdict — evidence pack assembled, human approval required, no live action without separate approval |

---

## Constitutional Constraints

All work under this change request must preserve the invariants defined in `CONSTITUTION.md`:

- Never claim guaranteed profit, zero loss, or zero drawdown.
- Never present backtest or demo results as live-profit evidence.
- No external model or repository may override risk controls.
- Every phase ends with exactly one verdict: `PASS_TO_NEXT_PHASE`, `CONDITIONAL_PASS`, `NO_GO`, `ARCHIVE_NO_EDGE`, or `INSUFFICIENT_SAMPLE`.
- Risk policy must be frozen and immutable.
- Pre-trade risk gate is mandatory before any order.
- Missing, invalid, or stale contract data must fail closed.
- Every sizing decision must bind to immutable contract snapshot ID.

---

## Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-07-01 | coordinator-agent | Initial change-control ticket created. References `Meta/GRAXIA_TSM_UNIFIED_MEGA_REMEDIATION_PLAN_2026-07-01.md` as the governing plan for unified GRAXIA-OS + TSM remediation. |

---

## Approval

| Approver | Role | Date | Decision |
|----------|------|------|----------|
| — | Human Reviewer | — | **PENDING** |

> No automated approval is sufficient. Human review and explicit sign-off is required before any live trading authorization or production credential use.
