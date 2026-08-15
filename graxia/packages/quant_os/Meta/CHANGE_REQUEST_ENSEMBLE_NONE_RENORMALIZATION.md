# Change Request: Ensemble None-Strategy Weight Renormalization

**Date:** 2026-07-24
**Author:** builder-agent (evidence-driven)
**Status:** PROPOSED
**Priority:** P1 (behavioral correctness, not safety-critical)

---

## Problem

When a sub-strategy in `StrategyEnsemble.get_ensemble_signal()` returns `None` (no trade), its registered weight remains in `total_weight` but contributes nothing to `buy_score`/`sell_score`. This causes two downstream effects:

1. **Confidence dilution:** `norm_buy = buy_score / total_weight` divides by 1.0 (all weights) even though one strategy contributed 0. The ensemble's effective confidence is lower than a renormalized calculation would produce.
2. **Weight map misreporting:** `indicator_values["weights"]` reports all three strategy weights (e.g. mtm=0.40, mrb=0.25, mlb=0.35) regardless of whether each contributed a vote. Downstream consumers (monitoring, logging, dashboards) cannot distinguish "MLB voted and got weight 0.35" from "MLB abstained and its 0.35 is dead weight."

**Current behavior (line 240 before the None-skip at line 241):**

```python
total_weight += rec.weight          # line 240 — runs unconditionally
if sig is None or sig.signal_type == SignalType.NO_TRADE:
    continue                        # line 241-242 — skips vote but weight already counted
```

**Concrete scenario:** MLB returns `None`. Ensemble has mtm=0.40, mrb=0.25, mlb=0.35. If MTM says BUY conf=0.8: `buy_score = 0.40*0.8 = 0.32`, `norm_buy = 0.32 / 1.0 = 0.32`. With renormalization: `norm_buy = 0.32 / 0.65 = 0.49`. The difference (0.32 vs 0.49) can push the ensemble below or above `confidence_threshold` (default 0.60), changing the trade/no-trade decision at the margin.

---

## Proposed Fix

Exclude None-returning strategies from `total_weight` and from the weights snapshot. Two-line change in `get_ensemble_signal`:

```python
# BEFORE (current):
total_weight += rec.weight          # line 240
if sig is None or sig.signal_type == SignalType.NO_TRADE:
    continue                        # line 241-242

# AFTER (proposed):
if sig is None or sig.signal_type == SignalType.NO_TRADE:
    continue
total_weight += rec.weight          # moved AFTER the None check
```

This excludes abstaining strategies from the denominator. `norm_buy = buy_score / total_weight` then divides by the sum of participating weights only. The fix is in `strategies/ensemble.py:240-242`.

---

## Behavioral Impact

### Going forward
- The ensemble's effective confidence changes when a strategy abstains. In the MLB=None scenario, confidence rises from 0.32 to 0.49 (example above). This can flip a NO_TRADE → BUY/SELL decision at the margin.
- `indicator_values["weights"]` should be updated to only report participating strategies' weights (or clearly distinguish abstaining from participating).

### Historical results caveat
Any prior backtest, paper-trade, or shadow-run result that was produced while:
- MLB was returning the hardcoded `0.75` (pre-fix era), OR
- MLB returned `None` with un-renormalized weighting (current era)

…used a different effective weighting than the corrected ensemble. **Pre-fix and post-fix numbers are not directly comparable.** A re-run with the corrected weighting is needed before any apples-to-apples performance claim. This should be noted in any report that compares pre-fix to post-fix results.

---

## Scope of Impact

- **File:** `strategies/ensemble.py` (1-2 line reorder)
- **Affected tests:** `tests/test_ensemble_c3.py` (27 tests) — may need adjustment if any test asserts specific norm_buy/norm_sell values with the old denominator.
- **Affected callers:** `get_ensemble_signal()` (legacy function at line 469) — same fix applies, both paths use the same `StrategyEnsemble.get_ensemble_signal()`.

---

## Evidence

- `strategies/ensemble.py:240-242` — `total_weight` accumulated before None-skip
- `strategies/ensemble.py:266` — `norm_buy = buy_score / total_weight` uses full denominator
- `strategies/ensemble.py:320-332` — `indicator_values["weights"]` reports all registered weights regardless of participation
- Reproduction: when MLB's `generate_signal()` returns `None` (model=None era), norm_buy/norm_sell are diluted by 0.35 in the denominator.

---

## Risk Assessment

- **Low risk:** This is a 1-2 line reorder in the voting path. No changes to strategy logic, risk policy, or order execution.
- **Correctness:** The fix matches standard weighted-voting semantics (abstentions don't count toward the total).
- **Regression:** All 27 ensemble tests currently pass; any test that asserts specific norm values may need updating to reflect the corrected denominator.

---

## Approval

| Approver | Role | Date | Decision |
|----------|------|------|----------|
| — | Human Reviewer | — | **PENDING** |
