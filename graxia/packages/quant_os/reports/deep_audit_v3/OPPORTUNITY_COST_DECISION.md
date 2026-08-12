# PHASE 24 — OPPORTUNITY COST & GO/NO-GO DECISION FRAMEWORK
*Per R1–R18. Tier 2. Forces an explicit, falsifiable decision.*

---

## 24.1 — Cumulative Multiple-Testing Tally

- **Total hypotheses tested across all sessions: UNKNOWABLE** — there is no hypothesis log (Phase 17.1). `scripts/build_features.py` alone defines ≥5 feature families; `scripts/research_*.py` (many), `scripts/optuna_tune.py`, `core/hyperopt.py` indicate extensive search.
- **Best estimate: dozens to low-hundreds of configurations/features tried.** Conservatively assume N ≥ 100.
- Apply Bonferroni to the best p-value ever observed: **no p-value was ever reported**, so the correction cannot be applied numerically — but if N≥100 and α=0.05, the corrected threshold is α/100 = 0.0005. **No finding in the repo approaches this.**
- The "58.2% accuracy" (`SUMMARY.md`) is not a p-value and on 67 trades is statistically fragile.

**Per protocol 24.1: "If the best result across dozens of configurations doesn't survive correction, that is the single most important sentence in the entire audit."** → **No reported result survives correction, because none was ever corrected and the best is a 67-trade point estimate.**

## 24.2 — Sunk Cost Check

- **Time invested**: from `git log`, the project has G0/G1/G2/G3/G4 phase progression, a `graxia_mega_plan_v3.md`, dozens of state files in `Meta/states/`, 813 Python files. This is **months of work**, not weeks. (Exact effort `[developer must confirm]`.)
- **Evidence accumulated about P(edge)**: net-negative on the only costed run (67 trades, −$23.21); no corrected significance; backtest/live parity broken; cost-model bugs.
- **Stated side by side**: months of work (irrelevant to the forward decision) vs. evidence that currently points to **no edge** (relevant). The contrast is the point — sunk cost must not justify continuation.

## 24.3 — Forward-Looking Decision Tree

Classification today, with cited evidence:

| Option | Applies? | Rationale |
|---|---|---|
| CONTINUE-SAME-APPROACH | **NO** | no statistically defensible post-correction signal exists (Phase 5, 6, 7, 13) |
| PIVOT-FEATURE-SPACE | maybe | only if a *specific, named* untested feature family has a stated rationale — `[none currently identified]` |
| PIVOT-INSTRUMENT-OR-TIMEFRAME | maybe | `SUMMARY.md:28-31` suggests EURUSD/GBPUSD (tighter spreads) and limit-orders as a named direction with a rationale (cost/move ratio). This is a legitimate candidate pivot. |
| **STOP** | **YES (default today)** | cumulative corrected evidence supports no further time investment in finding alpha *in the current XAUUSD M1 cost-dominant configuration* |

**Classification today: STOP (on the current XAUUSD-1min-cost-dominated configuration), with one named, testable exception — the PIVOT-INSTRUMENT direction (EURUSD/GBPUSD with tighter spreads + limit-order entries) that `SUMMARY.md` itself identifies.** This is a decision backed by evidence, not a vibe: the cost/move ratio of 83% on XAUUSD 1min is the structural reason, and tighter-spread FX majors address it directly.

**But — and this is the honest caveat — STOP vs PIVOT should not be decided by this audit alone. It should be decided by the result of the P0-1 label-shuffle test.** If the edge survives label-shuffling on XAUUSD, the cost problem is a *fixable* problem (better fills, wider barriers) and PIVOT-to-FX is worth trying. If it does NOT survive, neither XAUUSD nor FX is worth more time, and the answer is STOP. **Run the cheapest test first; let it decide.**

## 24.4 — Expected-Value Comparison

- vs zero-effort passive (not trading, or index fund): the current net expectation is **≤ 0**; the passive benchmark wins today. Over 1 year, not-trading ≈ 0–index-return; this system ≈ negative after costs.
- vs developer's other concurrent projects: `[developer must state what those are]`. The audit can only say the comparison is a *live decision*, not something to ignore.

## 24.5 — Kill Criteria (Set in Advance)

- **Existing kill criteria**: `reports/KILL_CRITERIA.md` exists → the concept is present. `[Contents not re-verified this phase per R5.]`
- **Recommendation**: set a concrete, dated kill criterion now, before more research. Example form:
  > "If no feature reaches BH-FDR-corrected significance with N≥500 OOS trades on EURUSD or GBPUSD M5/M15 by [date + 8 weeks of data collection], abandon this feature family and re-evaluate."

**Research without a pre-committed stopping rule is structurally biased toward 'just one more test.'** Set the rule before running P0-1.

---

## Phase 24 — Verdict

**Classification: STOP on the current configuration, with one evidence-named pivot candidate (FX majors + limit orders), and the decision between STOP and PIVOT deferred to the result of the P0-1 label-shuffle test (the cheapest possible disambiguation).** No further time should be invested in *building features* for XAUUSD-1min until (a) the label-shuffle test is run and (b) a pre-committed kill criterion is set. This is the honest, evidence-backed answer — not encouragement, not discouragement.
