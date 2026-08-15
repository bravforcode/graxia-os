# Stopping Rule — Pre-Registration

**Status:** LOCKED — 2026-07-12
**Hash (SHA-256):** `e2ba283ac8fdefef026eb17e99e2ecaf4b415d71e3ba43bec7f4bb8682baf39a`
**Cumulative trial count at lock:** 1002 (1001 from Search #1 + 1 from RYDC Arm A)

---

## 1. Purpose

Define pre-registered stopping criteria for edge discovery research. Without this, "keep searching until we find something" = meta-level p-hacking, even if each individual hypothesis is properly pre-registered.

**Scope:** applies to all future edge discovery work (Phase 3 of the system plan) for the `quant_os` trading system. Replaces ad-hoc decisions about when to stop testing hypotheses.

---

## 2. Sacred Holdout (Physical Separation)

| Property | Value |
|---|---|
| **Source data** | `data/rydc/rydc_daily.csv` (2018-01-02 to 2026-07-01, 2194 rows) |
| **Research data** | `data/rydc/rydc_research.csv` (2018-01-02 to 2025-06-30, 1934 rows) |
| **Sacred holdout** | `data/sacred_holdout/holdout.csv` (2025-07-01 to 2026-07-01, 260 rows) |
| **Access rule** | READ-ONLY until Phase 4.5 (final confirmation gate) |
| **Use count** | ONE. Opening this file and running backtests against it counts as 1 trial. Cannot be reopened. |
| **Reset** | None. If a candidate fails on holdout, the hypothesis is REJECTED permanently. No retesting. |

**Rationale:** DSR/WFE/PBO protect against overfitting within a single sample. They do not protect against "researcher degrees of freedom" — the risk that we unconsciously shape hypotheses to match what we've already seen in recent data. Sacred holdout is the only protection against this.

---

## 3. Stopping Rule (Pre-Registered)

Research stops when **ANY** of the following conditions is met:

### 3.1 Trial count limit

- **Maximum new hypotheses:** 20 (in addition to current 1002 cumulative)
- **Cumulative trial cap:** 1022 total
- After 20 new hypotheses fail to clear all gates, stop — no 21st test

### 3.2 Time limit

- **Maximum duration:** 3 months from Phase 3 start
- If 3 months elapse without a candidate passing all gates, stop

### 3.3 Resource limit

- **Maximum research hours:** 80 hours total
- Including: data exploration, hypothesis design, backtest runs, validation, debugging
- Does NOT include: paper trading wait time, live trading monitoring

### 3.4 Negative result trigger

If at any point **3 consecutive hypotheses** fail at the same gate (e.g., 3 in a row fail p-value gate), stop and re-examine:
- Is the gate correctly calibrated?
- Is the data quality sufficient?
- Is the entire research direction (e.g., XAUUSD cross-asset) misframed?

This prevents "death by a thousand cuts" — testing 20 hypotheses where 15 fail the same gate for the same underlying reason.

### 3.5 Stopping = archive, not continue

When stopping rule triggers, the conclusion is:
> **"No edge found within current resources. System is correctly built; edge does not exist (or is not accessible with public data + current methodology)."**

This is NOT a failure of governance. It is a valid scientific outcome. Do not "try one more thing."

---

## 4. Decision Protocol at Stop

When stopping rule triggers:

1. **Archive all results** to `reports/edge_search_2026/`
2. **Write final verdict document** with:
   - Total hypotheses tested
   - Distribution of failure modes (which gates failed most often)
   - Whether 3-in-a-row gate failure occurred (and which gate)
   - Honest assessment: was the search productive (learned something) or not
3. **Decision options:**
   - **A. Stop completely** — accept that edge is not accessible
   - **B. Change research direction** — requires new pre-registration, new stopping rule, fresh trial counter
   - **C. Wait for new data** — hold for 6-12 months, retry with expanded data
4. **No default is "continue with same approach"** — must explicitly choose A, B, or C.

---

## 5. Cumulative Trial Ledger

Current state (as of 2026-07-12):

| Trial # | Description | Result | Date |
|---|---|---|---|
| 1-1000+ | Search #1 (1000+ indicator combos) | FAIL | Pre-2026 |
| 1001 | RYDC Arm A (continuation) | FAIL (p=0.968) | 2026-07-12 |
| 1002+ | Reserved for future hypotheses | — | — |

**Rule:** All future hypotheses are trial #1003 onward, NO reset, NO fresh ledger. The cumulative count is the correct input to DSR.

---

## 6. Pre-Registration Lock

This document is locked at the timestamp above. Changes after lock are forbidden. If the stopping rule itself needs revision, the old version is archived, a new version is created with a new lock timestamp, and the trial count continues from the existing point.

**Verification:** hash of this document should match the hash in the system audit log. If mismatch, the document has been modified post-lock.

---

## 7. Acknowledgment

By locking this document, I acknowledge:

1. The null result from RYDC Arm A (p=0.968) is a **strong null result**, not "haven't found edge yet"
2. Further search with similar methodology has **low prior probability** of success
3. The 20-hypothesis cap is real, not aspirational
4. The sacred holdout is physically separated and must remain so until Phase 4.5
5. Stopping is a valid scientific outcome, not a failure
