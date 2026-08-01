# MEGA PLAN v3 — ERRATA ADDENDUM (v3)

**Date:** 2026-07-22 | **Applies to:** MEGA_PLAN v3 (draft, 2026-07-22)
**Basis:** File-level evidence check + executable numeric verification + git history analysis
**Status:** Incorporate into v3 before edge-discovery phase begins
**Supersedes:** v1 of this errata (corrects Erratum 1 and Erratum 3 from the first draft)

---

## Erratum 1: G3 (cost model bugs) — CLOSED (strengthened from v1)

**v3 claim:** "Known cost-model bugs (slippage≡spread conflation, 100x FX unit error) not required to be fixed before Phase 0A runs" — listed as CRITICAL blocker.

### 1a. The referenced file never existed

`backtest/slippage_model.py` — the file the audit attributed the "slippage≡spread conflation" bug to — **has no git history at all**:

```
$ git log --all --oneline -- "backtest/slippage_model.py"
(no output)
```

This was a hallucinated file path. The actual slippage model lives at `core/slippage_model.py` (exists since earlier commits, visible at HEAD). `backtest/dynamic_spread_model.py` was created as a **new file** in commit `05824e28` (the security/audit fix wave) — `git log --follow --diff-filter=R` shows no rename from any prior file.

**Conclusion:** The "slippage≡spread conflation" bug either never existed at the path cited, or was fixed before the git history window. Either way, the current code is correct.

### 1b. No 100× FX unit error — verified with hand-calculated reference case

**Not just a code read-through.** Ran executable test with known reference values:

| Scenario | Hand calculation | Function output | Match? |
|----------|-----------------|-----------------|--------|
| EURUSD 1 std lot (spread=1pip, comm=$7) | spread=$10.00, slip=$3.00, comm=$7.00, total=$20.00 | spread=$10.00, slip=$3.00, comm=$7.00, total=$20.00 | ✅ |
| XAUUSD 1 std lot (spread=3.5pips, comm=$0) | spread=$35.00, slip=$10.50, total=$45.50 | spread=$35.00, slip=$10.50, total=$45.50 | ✅ |
| EURUSD 1 std lot 2× stress | spread=$20.00, slip=$6.00, comm=$7.00, total=$33.00 | spread=$20.00, slip=$6.00, comm=$7.00, total=$33.00 | ✅ |

If a 100× error existed, EURUSD total would be $2,000 or $0.20 instead of $20.00. It isn't.

**Action:** G3 is CLOSED. Remove from CRITICAL blocker list. Task 0-Pre.7 becomes a verification task (confirm stability), not a fix task.

---

## Erratum 2: Annualization bug blast radius — LIMITED TO REPORTING, NOT VERDICTS (unchanged from v1)

**v3 claim:** "backtest_suite.py:127 annualizes with sqrt(252*96) — a factor meant for 15-minute intraday bars — applied to daily data."

**The bug is real.** `backtest_suite.py:127`:
```python
sharpe = float(np.sqrt(252*96) * strat.mean() / strat.std())  # WRONG: 155.5× instead of 15.87×
```

**But the blast radius does NOT extend to formal trial verdicts.** Two separate Sharpe computation paths exist:

| Path | Formula | Used by |
|------|---------|---------|
| `scripts/backtest_suite.py:127` | `sqrt(252*96)` ❌ | Quick multi-strategy backtests, Phase 9's "Real backtest Sharpe" column |
| `scripts/edge_search_all.py:543,609` | `sqrt(252)` ✅ | All 17 DK-test strategies, pooled t-stat, per-asset Sharpe counts, label-shuffle verdicts |

**Arithmetic cross-check (independently confirmable):**
- Phase 9 reported "BTCUSD Real backtest Sharpe: 2.84" and "Label-shuffle Sharpe: 0.2897"
- 2.84 / 0.2897 = 9.80
- √96 = 9.80
- This is exactly the signature of two return series run through two different annualization factors — one buggy (√(252×96)), one correct (√252). The label-shuffle test independently computed its own Sharpe using the correct formula.

**Action:** Fix `backtest_suite.py:127` to `sqrt(252)` as a P2 reporting bug. Do NOT re-derive any REJECTED verdict — they were computed correctly.

---

## Erratum 3: Trial #2001 dk_t — CORRECTED (v1 had wrong number)

**v1 of this errata** stated: "Trial #2001 (EDGE_SEARCH_FINAL)... Best dk_t = -0.22 (RSI_20_80)."

**This was wrong.** The -0.22 figure belongs to RSI_20_80, one of 17 strategies in the EDGE_SEARCH_FINAL run — NOT Trial #2001.

### Clean citation — Trial #2001

**`CHANGE_CONTROL.md:97`:**
> Trial #2001 REJECTED — Cross-Sectional Momentum (momentum_factor_rotation). dk_t = -2.1255 (required > 2.0). Pooled Sharpe = -1.5357 (required > 0). Positive Sharpe count = 2/7 (required >= 5).

**`hypothesis_registry.json:215-247`:**
> trial_id: 2001, id: "MULTI-ASSET-TSMOM-RANKING", dk_t: -2.1255, pooled_sharpe: -1.5357, positive_sharpe_count: 2, verdict: "REJECT"

### Clean citation — RSI_20_80 (different trial family)

**`EDGE_SEARCH_FINAL_20260718.md:33`:**
> RSI_20_80 | 214 trades | dk_t = -0.22 | pooled_sharpe = -0.61 | pos_sharpe = 0/6 | REJECT

**These are different trials.** Trial #2001 is cross-sectional momentum with dk_t = **-2.1255**. RSI_20_80 is a single-asset RSI strategy with dk_t = -0.22. The errata v1 conflated them.

### Additional finding: trial-ID collision — FIXED

`trial_ledger_c.json:27` has Trial #2001 as `btc_vol_divergence` (p=0.5533, 2026-07-13).
`hypothesis_registry.json:215` has Trial #2001 as `MULTI-ASSET-TSMOM-RANKING` (dk_t=-2.1255, 2026-07-20).

Two different trials, same number. Root cause: two parallel ledger files (`trial_ledger*.json` and `hypothesis_registry.json`) both use bare int trial IDs with no cross-file uniqueness enforcement.

**Fix:** `scripts/check_trial_uniqueness.py` — scans all ledgers, reports collisions. Run output (2026-07-22):

```
Trial #2001: conflicting ids = ['btc_vol_divergence', 'MULTI-ASSET-TSMOM-RANKING']
  source=trial_ledger_c.json  id=btc_vol_divergence  result=REJECTED  date=2026-07-13
  source=hypothesis_registry.json  id=MULTI-ASSET-TSMOM-RANKING  result=REJECTED  date=2026-07-20

Trial #2003: same id casing mismatch + result mismatch (REJECTED vs INSUFFICIENT_DATA)
```

Also caught 2 naming-convention mismatches (trials #2002, #2003: `snake_case` vs `UPPER-KEBAB`) and 1 result mismatch (#2003: `REJECTED` vs `INSUFFICIENT_DATA`).

**Structural fix options** (pick one, apply before any new trial is registered):
1. Merge to single source-of-truth ledger (eliminate parallel files)
2. Namespace IDs by source file (`hyp-2001` vs `ledger-2001`)
3. Add uniqueness check to CI/pre-commit (script already exists)

### Corrected comparison table

| Dimension | Phase 9 (label-shuffle) | Trial #2001 (DK-test) |
|-----------|------------------------|----------------------|
| **Strategy** | Single-asset absolute momentum (price > MA(12) → long) | Cross-sectional relative momentum (rank 7, long top 2) |
| **dk_t** | Not computed (per-symbol Sharpe only) | **-2.1255** (not -0.22) |
| **Pooled Sharpe** | Not computed | **-1.5357** |
| **pos_sharpe** | 5/7 positive (none significant) | **2/7** |
| **Verdict** | NO EDGE (single-asset) | REJECT (cross-sectional) |

**Action:** `scripts/check_trial_uniqueness.py` now exists and catches the collision. Structural fix (merge ledgers / namespace IDs / CI check) should be applied before any new trial is registered. Use this script as a gate before edge discovery — run it first, fix collisions, then proceed.

---

## Erratum 4: Path B viable candidate list — 2 of 8, not 8 of 8 (unchanged from v1)

**v3 claim:** "8 external edges" proposed by the deep-research document.

**After citation verification (Task 0-Pre.5), the actual viable list:**

| # | Edge | Citation status | Viable for this system? |
|---|------|----------------|------------------------|
| 1 | Cost-aware signal filtering | ❌ Fabricated journal/author | **No** |
| 2 | Dynamic regime-adaptive ensemble | ⚠️ Real paper, wrong numbers + wrong asset class | **No** (for XAUUSD/FX/Indices) |
| 3 | Order-book imbalance (OBI) | ✅ Real, foundational | **No** (requires L2 data this system doesn't have) |
| 4 | VPIN (flow toxicity) | ✅ Real, foundational | **No** (requires L2 data this system doesn't have) |
| 5 | ML alpha / cost-aware objectives | ✅ Real, reasonable framing | **Maybe** (no importable return number) |
| 6 | RL execution / meta-adaptive agents | ✅ Real, reasonable framing | **Maybe** (equities-focused, not validated for MT5/FX) |
| 7 | Funding rate arbitrage | ⚠️ Blog source, not academic | **Weak** (directional only, no peer review) |
| 8 | On-chain analytics | ⚠️ Blog source, not academic | **Weak** (directional only, no peer review) |

**Viable Path B candidates: 2** (ML alpha signals, RL execution) — and even these come with no importable return-uplift number.

---

## Summary of corrections to v3

| v3 item | Correction | Verification method | Impact on plan |
|---------|-----------|-------------------|----------------|
| G3 (CRITICAL blocker) | Closed — `backtest/slippage_model.py` never existed; cost model files correct; no 100× error | git log + executable numeric test (3 reference cases) | Remove from blocker list |
| Annualization bug | Real bug, blast radius limited to reporting | Arithmetic cross-check (2.84/0.2897 = √96) | Fix as P2; verdicts untouched |
| Trial #2001 dk_t | **-2.1255** (not -0.22); -0.22 belongs to RSI_20_80 | CHANGE_CONTROL.md:97 + hypothesis_registry.json:234 | Collision caught by `scripts/check_trial_uniqueness.py` — structural fix needed before next trial |
| Trial-ID collision | 3 collisions found (1 real, 2 naming mismatches, 1 result mismatch) | Executable script output | Script exists; structural fix options documented (merge ledgers / namespace / CI check) |
| Phase 9 vs #2001 | Distinct hypotheses (absolute vs relative momentum) | Mechanism comparison | Edge-discovery phase must compare mechanism, not just universe |
| Path B candidate list | 2 viable candidates, not 8 | Citation verification | Shrink roadmap |

---

**Generated:** 2026-07-22 (v2 — corrected Trial #2001 dk_t and strengthened G3 closure)
**Verification methods:** git log --follow, executable numeric test, arithmetic cross-check, direct file:line citation
**Next:** Incorporate into v3 before edge-discovery phase begins
