# Phase -1 Reconciliation — Trial #2001 Status

**Date:** 2026-07-22 | **Status:** COMPLETE
**Verdict:** Trial #2001 is ALREADY ANSWERED — ARCHIVE_NO_EDGE

---

## What was checked

Three questions:
1. What strategy did Phase 9's label-shuffle test actually test?
2. Is that the same hypothesis as Trial #2001?
3. Was Trial #2001 ever tested with a label-shuffle?

---

## Finding 1: Phase 9 and Trial #2001 are DIFFERENT hypotheses

| Dimension | Phase 9 (label-shuffle) | Trial #2001 (DK-test) |
|-----------|------------------------|----------------------|
| **Strategy** | `backtest_momentum()` from `backtest_suite.py` | `momentum_factor_rotation.py` |
| **Signal** | `price > MA(12)` → long, else flat | Multi-asset TSMOM with ranking (lookbacks 21/63/252) |
| **Type** | Single-asset absolute momentum | Cross-sectional relative momentum |
| **Vol targeting** | None | 0.10 annualized |
| **Rebalance** | Every bar (daily) | Every 5 bars (weekly) |
| **Top_n** | N/A (binary in/out) | 2 (long top 2 of 7) |
| **Test method** | Per-symbol Sharpe vs iid-shuffled null | Pooled DK-t with Newey-West HAC |

**Conclusion:** Phase 9 does NOT answer Trial #2001. They are different mechanisms.

---

## Finding 2: Trial #2001 was ALREADY tested and rejected

**`reports/edge_search_cross_sectional_20260720.json`:**
```json
{
  "trial_id": 2001,
  "strategy": "momentum_factor_rotation",
  "parameters": {
    "lookbacks": [21, 63, 252],
    "vol_target": 0.1,
    "top_n": 2,
    "bottom_n": 0,
    "rebalance_freq": 5,
    "min_signal_strength": 0.3
  },
  "pooled": {
    "dk_t": -2.1255,
    "pooled_sharpe": -1.5357,
    "positive_sharpe_count": 2,
    "total_trades": 3000,
    "verdict": "REJECT"
  },
  "label_shuffle": {
    "n_shuffles": 200,
    "observed_sharpe": -1.5357,
    "p_value": 0.0,
    "verdict": "PASS"
  },
  "combined_verdict": "REJECT"
}
```

**Key facts:**
- Trial #2001 was tested on 2026-07-20 (2 days before this session)
- dk_t = -2.1255 (required > 2.0) — **FAILED**
- pooled_sharpe = -1.5357 (required > 0) — **FAILED**
- positive_sharpe_count = 2/7 (required >= 5) — **FAILED**
- Label-shuffle: p = 0.0, observed_sharpe = -1.5357 — strategy is significantly WORSE than random
- Combined verdict: **REJECT**

**NAS100 lost 99.99%, US30 lost 95.60%.** The strategy didn't just fail to have an edge — it was catastrophic.

---

## Finding 3: The cost model used in Trial #2001 is correct

The errata v3 confirmed:
- `backtest/slippage_model.py` never existed (hallucinated path)
- `execution/cost_model.py` and `core/cost_model.py` are correct
- No 100× FX unit error (verified with executable numeric test)
- The "slippage≡spread conflation" bug was fixed (documented in `core/cost_model.py:3-5`)

**The cost model used in Trial #2001 is trustworthy.** The REJECT verdict was not produced by a buggy cost model.

---

## Determination

| Question | Answer |
|----------|--------|
| Does Phase 9 answer Trial #2001? | **No** — different hypotheses (absolute vs relative momentum) |
| Was Trial #2001 already tested? | **Yes** — 2026-07-20, with label-shuffle |
| Was the cost model correct? | **Yes** — verified by executable numeric test |
| What was the verdict? | **REJECT** — dk_t = -2.1255, catastrophic losses on NAS100/US30 |

**Phase -1 verdict: Trial #2001 is ALREADY ANSWERED.**

Phase 0A of MEGA_PLAN v3 would be re-testing an already-rejected hypothesis with an already-verified cost model. This is the exact scenario the plan was designed to catch — spending 2.5-3 weeks discovering what's already known.

---

## Recommended next steps

1. **ARCHIVE_NO_EDGE** for Trial #2001 in `hypothesis_registry.json` (already marked REJECTED)
2. **Proceed to Business Reality Check** (MEGA_PLAN v3 §Business-Level Reality Check):
   - **Path B — Import published edge:** ML alpha (Khubiev et al.) or RL execution (Chen et al. MARS). These are real, peer-reviewed papers with reasonable framing. No importable return number, but the mechanisms are sound.
   - **Path C — Reallocate time:** Graxia OS / AdminMate have commercial traction. 18+ weeks chasing a null result in saturated retail FX/CFD market is a real opportunity cost.
3. **Fix `backtest_suite.py:127`** — `sqrt(252*96)` → `sqrt(252)` (P2 reporting bug, 5 minutes)
4. **Run `scripts/check_trial_uniqueness.py`** — fix the 3 trial-ID collisions before registering any new trial
5. **Apply structural fix** to trial ledger (merge files / namespace IDs / CI check)

---

## Files referenced

- `reports/edge_search_cross_sectional_20260720.json` — Trial #2001 full results
- `hypothesis_registry.json:215-247` — Trial #2001 registration
- `CHANGE_CONTROL.md:97` — Trial #2001 REJECTED entry
- `strategies/momentum_factor_rotation.py` — Strategy implementation
- `scripts/backtest_suite.py:50-60` — Phase 9's `backtest_momentum()` implementation
- `MEGA_PLAN_v3_ERRATA_20260722.md` — Cost model verification

---

**Generated:** 2026-07-22
**Basis:** Direct file:line inspection + executable numeric verification
**Conclusion:** ARCHIVE_NO_EDGE — Trial #2001 is answered, Phase 0A is moot
