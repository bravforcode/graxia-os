# PHASE 13 — ADVERSARIAL / RED-TEAM STRESS TESTING
*Per R1–R18. The cheapest, highest-leverage phase for protecting capital.*

---

## 13.1 — Label/Target Shuffling (Null Hypothesis Sanity Check)

**The test EXISTS as code** — `tests/test_label_shuffling.py:18-69` `run_label_shuffle_test`:
- Shuffles labels via `np.random.permutation(labels)` (`test_label_shuffling.py:44`).
- Default `n_permutations=100` (`test_label_shuffling.py:23`) — meets the ≥100 protocol minimum.
- Computes `null_95th_percentile` and `p_value = (null_sharpes >= real_sharpe).mean()` (`test_label_shuffling.py:53,56`).
- `survives = real_sharpe > null_95th and p_value < 0.05` (`test_label_shuffling.py:59`).

**This is correctly implemented per the protocol's spec.** It is the single most important adversarial test, and it is present.

**But: has it been RUN and a result recorded?** `[NO RESULT ARTIFACT FOUND]` — no `*label_shuffle*` JSON/report in `reports/`, `results/`, or `artifacts/`. The test exists; there is no evidence it has been executed against the current best config and a `survives=True/False` verdict recorded.

Per protocol 13.1: *"If this test has never been run: this is a **P0 finding**. No claimed edge in this codebase can be trusted until it survives this test."*

**→ P0.** The test is built but its result is unknown. Until it is run and the real Sharpe is shown to fall OUTSIDE the null distribution, no edge claim is valid. **This is the single cheapest check that could either confirm or kill the project's edge thesis, and it has not been executed.**

**Seed**: `np.random.permutation` uses the global numpy RNG. `test_label_shuffling.py` does NOT call `np.random.seed()` → **result is non-reproducible run-to-run** (Phase 17.2/19). Running it twice gives different null distributions. → P2 (reproducibility), trivially fixable.

## 13.2 — Synthetic / Surrogate Data Injection

`[NOT FOUND]`. No GARCH-simulated / randomized-phase Fourier surrogate test in `scripts/` or `tests/`. The capability to generate synthetic series with matched vol/autocorrelation is absent. → P2.

## 13.3 — Cost & Friction Perturbation

- `cost/cost_stress_analyzer.py`, `validation/cost_stress.py`, `cost_model.py:ALL_SCENARIOS` (1×, 1.5×, 2×, 3×) exist → **capability present and structured**.
- Protocol asks for 0.5×–5×. Code defines up to 3× (`STRESS_3`). 5× not covered.
- **Has the matrix been run on the current best config and the zero-crossing multiplier reported?** `[NOT FOUND in any artifact]`. → P1.

## 13.4 — Outlier / Single-Trade Sensitivity

`[NOT FOUND as a script]`. No "remove best trade / best week, recompute Sharpe" routine. Given the only costed run had **67 trades** (`SUMMARY.md`), single-trade sensitivity is *especially* material (one trade = 1.5% of sample). → P1.

## 13.5 — Time-Period Sensitivity ("Delete the Best Month")

`[NOT FOUND]`. And moot on the current 7-day M1 window — there are no "months" to delete. → P3 (becomes P1 once multi-month data exists).

## 13.6 — Parameter Perturbation Stability

- `core/param_sweep.py`, `validation/parameter_stability.py` exist → capability present.
- The ±10%/±20% perturbation grid with numeric Sharpe surface: `[NOT RUN/REPORTED]`. → P1.

## 13.7 — Adversarial Summary Table

| Stress Test | Run? | Result | Survives? |
|---|---|---|---|
| Label shuffling (null distribution) | **Code exists, NOT RUN** | unknown | **UNVERIFIED → P0** |
| Synthetic/surrogate data | NO | — | UNVERIFIED |
| Cost perturbation (0.5×–5×) | Code exists (up to 3×), NOT RUN | unknown | UNVERIFIED |
| Best-trade / best-week removal | NO | — | UNVERIFIED |
| Leave-one-month-out | N/A (7-day data) | — | N/A |
| Parameter perturbation ±10–20% | Code exists, NOT RUN | unknown | UNVERIFIED |

---

## Phase 13 — Verdict

**STATUS: BLOCKED (P0).** The adversarial framework is *partially built* (label-shuffle test, cost-stress scenarios, param-sweep modules all exist), but **none of the tests have been executed against the current best configuration and had their results recorded.** 

Per the protocol's own emphasis, the label-shuffle test is "the single cheapest, hardest-to-fake check available" — it is present in the repo and has still not been run. **Until it is, every claim of edge in this codebase is unverified, and the protocol explicitly classifies this as a P0 blocker.**
