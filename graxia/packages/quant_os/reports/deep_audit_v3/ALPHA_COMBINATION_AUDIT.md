# PHASE 14 — ALPHA COMBINATION & ENSEMBLE CONSTRUCTION AUDIT
*Per R1–R18. Tier 3.*

---

## 14.1 — Combination Methodology
- `core/config.py:71-77` `strategy_weights` = **fixed-weight ensemble** (mtm 0.40, mrb 0.25, mlb 0.35). `strategies/ensemble.py` implements it. Weights are **hardcoded**, not fit per-fold.
- `core/orchestrator.py` exists for multi-agent orchestration. `[Combination logic not fully traced]`.
- **Were weights fit on data used to validate features?** Weights are fixed constants, not data-fit → no *additional* leakage from the combination step itself. (The individual features may still be overfit — Phase 5/6.)

## 14.2 — Independence of Combined Signals
- `core/correlation.py` exists. **Inter-feature correlation matrix: `[NOT REPORTED]`.** MTM/MRB/MLB are nominally different (momentum / mean-reversion / breakout) but mean-reversion and momentum are often strongly negatively correlated — "combining" them may be largely offsetting rather than diversifying. → P2.

## 14.3 — Marginal Contribution Test
- `[Ablation study NOT FOUND]`. No "remove component X, recompute OOS" result. → P2.

## 14.4 — Ensemble-Level Multiple Testing
- Multiple combination methods tried? `strategies/ensemble.py` + fixed weights suggest one method. `[Only one ensemble method evident]` → less exposure here, but the *selection of the fixed weights themselves* (0.40/0.25/0.35) is an untested choice that should be folded into the trial count.

---

## Phase 14 — Verdict

**STATUS: PARTIAL / low-priority.** Combination is fixed-weight (low leakage risk from the combination step), but no independence check, no ablation, no inter-feature correlation reported. **More importantly: ensembling is premature when no component has a confirmed edge** — combining three unproven signals does not produce a proven ensemble. Address Phase 5/6/13 first.
