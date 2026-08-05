# Go-Live Gate — Corrected Sequencing & Blocker Methodology

**Purpose of this addendum:** fix the internal contradiction in the original timeline, and supply concrete methodology for the two items (A1, A5) that were listed as blockers but had no defined procedure.

---

## 0. Pattern to audit before trusting any other PROMOTE/PASS label

The cost-model bug (`cost = 0.00001` default silently driving "PROMOTE" for XPDUSD/XPTUSD, off by ~5000x from measured 45–55 bps) is the same failure class as a DSR gate bug found earlier today in the XAUUSD/RYDC validation pipeline: a placeholder value substitutes for a real measurement, and produces a decision label that looks like evidence but isn't.

**Before proceeding with anything else:**
```
grep -rn "0.00001\|dummy\|placeholder\|TODO\|FIXME" --include=*.py .
```

Cross-reference every hit against Category F (stub list) and B2 (`evaluate_model()` dummy metrics) — B2 is very likely the same bug class: if champion/challenger comparison runs on dummy metrics, no promotion decision made through that path should be trusted either, retroactively.

### Bugs Found (2026-07-12)

| Bug | File | Line | Impact |
|---|---|---|---|
| `evaluate_model()` returns dummy `deflated_sharpe=1.0` | `scripts/auto_retrain.py` | 72-81 | Champion/challenger comparison meaningless — any promotion through this path is fake |
| Default cost `{"spread": 1e-05, "slippage": 3e-05}` | `scripts/run_multi_instrument_wf.py` | 348 | If symbol not in cost_calibration.json, uses 0.001 bps instead of real cost |
| Placeholder strategies for crypto/forex/indices | `alpha/engine.py` | 571-610 | `_placeholder_crypto/forex/indices()` — not real strategies |

**Status:** XPDUSD and XPTUSD ARE in `cost_calibration.json` with real measured costs (110.70 bps and 90.58 bps RT). The default fallback at line 348 may not have been triggered for these specific symbols — but the pattern exists and should be fixed.

---

## 1. Sequencing fix

Original timeline has a direct contradiction: Week 3 says "GATE CHECK — if no edge, STOP," Week 3–4 says bug-fixing continues regardless. Resolve explicitly:

| If A1–A6 result | Then |
|---|---|
| **FAIL** (no instrument clears real-cost validation) | Real stop. Categories B (except carve-out below), C, D, E, G all pause. Effort redirects to either a new instrument/strategy search (new pre-registration, fresh trial-count ledger) or shutting this direction down. |
| **PASS** (at least one instrument clears) | Proceed to B–G as originally scheduled, gated on the specific instrument(s) that passed — do not silently extend infra work to instruments that failed A1–A6. |

**Safety carve-out — do regardless of A1–A6 outcome, before any further paper trading:**
- B7 (kill-switch state-corruption recovery test)
- B1 (alert routing — P0/P1 alerts must not silently vanish)

These aren't "go-live" bugs, they're "the paper-trading process itself is unsafe to run unattended" bugs. Everything else in B–G can genuinely wait for the A gate.

---

## 2. A1 — Real Spread Measurement Protocol

**Do not use a single snapshot or a broker's advertised "average."** Measure from your own live tick feed.

- **Instruments:** XAUUSD, XPDUSD, XPTUSD (same three already in scope)
- **Duration:** minimum 7 full calendar days, must include: Asian session, London session, NY session, London/NY overlap, Friday close → Sunday reopen gap
- **What to log per tick:** timestamp (UTC), bid, ask, computed spread in both raw price and bps of mid
- **Aggregate by session bucket, not one flat average** — spread is not constant through the day. Report at minimum: mean, median, 90th percentile, max, broken out by session (Asian / London / NY / rollover). A strategy that trades disproportionately during one session needs that session's spread, not the 24h blend — using the blended average will still misprice cost if your entry signals cluster at specific hours (worth checking: does RYDC-style z-score entry cluster around any particular session for these metals?).
- **Commission:** add the fixed per-side commission (e.g., Pepperstone Razor's $3.50/lot/side, confirmed in an earlier session for XAUUSD/FX) converted to bps at your typical trade size — do not fold this into the spread number, keep them as separate cost components so either can be updated independently later.
- **Slippage:** if any live/demo order history exists, extract realized slippage (fill price vs. signal price) separately — this is a third cost component, distinct from spread and commission, and the walk-forward in A2 needs all three, not spread alone.
- **Output:** a per-instrument, per-session cost table (mean/median/p90 in bps) that A2 consumes as an input — not a single constant.

### Implementation

```python
# scripts/measure_real_spread.py
# Output: config/cost_calibration_measured.json
# Schema:
# {
#   "XAUUSD": {
#     "asian": {"mean_bps": ..., "median_bps": ..., "p90_bps": ..., "max_bps": ...},
#     "london": {...},
#     "ny": {...},
#     "rollover": {...},
#     "commission_bps_per_side": ...,
#     "slippage_bps_measured": ...
#   },
#   ...
# }
```

---

## 3. A5 — Multiple Testing Correction, Worked

**Clarify the test family first — this determines the correction:**
1. Is this 13 instruments × 1 fixed strategy (13 tests total)? Or 13 instruments × multiple timeframes (H1/D1/M15 mentioned → up to 39 tests)? State the exact family size before correcting anything.
2. **Does this scan share lineage with the earlier XAUUSD 1000+-combo parameter search / RYDC hypothesis?** If the strategy being tested across these 13 instruments was itself the winner selected from that earlier search, this is a continuation of the same research program — trial count should compound (same logic as RYDC being tagged "trial #1001+"), not reset to a fresh family of 13. If it's a genuinely independent strategy design never involved in that earlier search, it can get its own ledger. This needs an explicit answer, not an assumption either way.

**Correction math, once family size N is fixed:**
- **Bonferroni (conservative, family-wise error control):** required per-test significance = 0.05 / N. For N=13: **p < 0.00385**. For N=39: **p < 0.00128**.
- **Benjamini-Hochberg (less conservative, false-discovery-rate control)** — usually more appropriate for an exploratory instrument scan like this: sort the N p-values ascending, find the largest k such that p(k) ≤ (k/N)·0.05, reject (i.e., treat as a genuine candidate) all tests with p ≤ p(k). Standard implementation: `scipy.stats.false_discovery_control` or `statsmodels.stats.multitest.multipletests(pvals, method='fdr_bh')`.
- If lineage with the earlier search is confirmed (per point 2 above), N should include the cumulative count from that search, not just 13 — same principle as the DSR trial-count fix applied to RYDC.

### Implementation

```python
# In run_multi_instrument_wf.py, after collecting all p-values:
from scipy.stats import false_discovery_control

pvals = [r["p_value"] for r in all_results if r["status"] == "OK"]
# BH correction
adjusted_pvals = false_discovery_control(pvals, method='bh')
# Bonferroni
bonferroni_threshold = 0.05 / len(pvals)
```

---

## 4. On "developing the best strategy"

Not answerable yet with current information. As of this document, XAUUSD D1 is unmeasured, XPDUSD/XPTUSD D1 both REJECT, and every H1 "PROMOTE" result is currently unverified because it ran on the placeholder cost. There is no instrument yet with a real-cost-adjusted, statistically-corrected PASS to call "best" — the honest next deliverable is "does anything clear A1–A6," not a strategy recommendation. Revisit this question after that gate resolves, one way or the other.

---

## 5. Immediate Actions (Priority Order)

1. **Fix `auto_retrain.py:evaluate_model()`** — implement real model evaluation, not dummy metrics
2. **Fix `run_multi_instrument_wf.py:348`** — fail loudly if symbol not in cost_calibration.json, don't silently use default
3. **Run A1 spread measurement** — 7 days minimum, all sessions
4. **Re-run A2 with real costs** — after A1 completes
5. **Apply A5 correction** — after A2, with correct trial count lineage
6. **Safety carve-out** — B7 (kill-switch) and B1 (alerts) regardless of A gate outcome

---

## 6. Phase 1 Completion Notes (2026-07-13)

**Status:** A1, A2, A5 still pending (waiting on spread measurement window + cost calibration). Items 1, 2, and 6 above are DONE. This section is the record of what was actually re-verified and what artefacts now exist for the safety carve-out.

### 6.1 Bug fixes confirmed in place

| # | Bug | File | Status |
|---|---|---|---|
| 1 | `evaluate_model()` returns dummy `deflated_sharpe=1.0` | `scripts/auto_retrain.py:72-181` | **FIXED** — now returns `nan_metrics(deflated_sharpe=NaN)` on any failure path; DSR computed via `scipy.stats.norm.cdf` from a properly scaled z-score (E[max SR] scaled by `sr_se`, not raw quantile). |
| 2 | Default cost `{"spread": 1e-05, "slippage": 3e-05}` silently used | `scripts/run_multi_instrument_wf.py:346-365` | **FIXED** — `_DEFAULT_COSTS` retained only for explicit `--allow-default-costs` flag (testing); default behaviour now returns `status="NO_COST_DATA"` and skips the symbol with an `ERROR` line. XPDUSD/XPTUSD/XAUUSD are in `cost_calibration.json` so they do not hit this path. |
| 3 | DSR formula in `scripts/run_rydc_validation.py:496-539` | — | **FIXED** — `e_max_sharpe` now scaled by `sr_se`; previously DSR collapsed to ~1.4e-116 (numerical zero) for any realistic input. |
| 4 | PBO `NaN` reported as PASS | `validation/pipeline/gates.py` and downstream consumers | **FIXED** — PBO is now correctly classified as `INSUFFICIENT_DATA` when only a single config is available. |
| 5 | WFE bound missing | walk-forward / gates | **FIXED** |
| 6 | Cost fallback | run_multi_instrument_wf.py | **FIXED** (same as #2) |

### 6.2 Remaining default/placeholder patterns (audit, 2026-07-13)

Re-ran `rg "0\.00001|dummy|placeholder" --include "*.py"` across the repo. The patterns that survive and their disposition:

| File | Line | Pattern | Disposition |
|---|---|---|---|
| `alpha/engine.py` | 571-610 | `_placeholder_crypto/_placeholder_forex/_placeholder_indices` | **OUT OF SCOPE for Phase 1** — these are not safety bugs (they `raise NotImplementedError`); they only matter if/when crypto/forex/indices enter the trade universe. Keep flagged. |
| `api/orders.py` | 72-73 | "For now, return placeholder" + `raise HTTPException(501)` | **SAFE** — endpoint returns 501 Not Implemented, never silently accepts an order. |
| `broker/mt5_gateway.py` | 98 | `snapshot_hash=""` placeholder, computed below | **SAFE** — overwritten in the very next line by `compute_snapshot_hash(spec)`. |
| `live_readiness/symbol_snapshot_service.py` | 131 | same `snapshot_hash=""` pattern | **SAFE** — same overwrite-immediately pattern. |
| `live_readiness/account_snapshot_service.py` | 105 | same pattern | **SAFE** — same. |
| `markets/eurusd/contract_snapshot.py` | 16 | `tick_size = Decimal("0.00001")` | **NOT a placeholder** — this is the real EURUSD 5-decimal pipette. |
| `execution/reconciler.py` | 15 | `DEFAULT_PRICE_TOLERANCE = Decimal("0.00001")` | **NOT a placeholder** — explicit tolerance constant for reconciliation, named. |
| `tick/tick_schema.py` | 50 | `0.00001` divider for spread-to-pipette | **NOT a placeholder** — domain math. |
| `risk/position_sizer_v2.py` | 236 | "Basic margin check (placeholder)" comment | **KNOWN, NOT A BUG** — code-level comment documents that the full margin check is deferred to `pre_trade_risk.py` where equity lives. Comment is accurate. |
| `validation/live/__init__.py` | 234 | "placeholder result indicating manual testing needed" | **NOT A BUG** — explicit `manual_testing_required` flag in the live validation framework; not on the hot path. |
| `strategies/walk_forward.py` | 272 | "simulate simple trade: entry at current, exit 5 bars later (placeholder)" | **OUT OF SCOPE** — only used inside walk-forward's internal diagnostic harness, not in any live/paper path. |
| `strategies/mlb.py` | 380 | `train()` returns `{"accuracy":0,"precision":0,"recall":0}` placeholder | **KNOWN LIMITATION** — `MLB.train()` is not wired to the real training pipeline; the real training is in `scripts/train_*.py`. `mlb.py` is a signal consumer, not a trainer. Documented in `KNOWN_LIMITATIONS.md`. |
| `data/sacred_holdout/holdout.csv` | — | (referenced for context only) | **SACRED** — DO NOT TOUCH. Phase 4.5 only. |
| `tests/`, `scripts/prepare_rydc_data.py` | many | `X_dummy`, "Create dummy DFII10 data", etc. | **TEST/SCRIPT DATA** — explicitly not production. |

**No new production-code placeholder bugs found.** The audit is closed.

### 6.3 Validation results re-check (DSR + WFE + PBO fixed gates)

Existing `reports/validation/*.json` files and their compatibility with the fixed gates:

| File | DSR value | DSR threshold used | Status | Re-run needed? |
|---|---|---|---|---|
| `20260707_202008_validation_report.json` | -2.1933 | (raw z-score, not probability) | produced by old pipeline | **YES** — used pre-fix `validation/deflated_sharpe.py` |
| `20260707_202049_validation_report.json` | -2.1933 | (raw z-score) | same | **YES** |
| `20260707_202131_validation_report.json` | -2.1933 | (raw z-score) | same | **YES** |
| `20260707_204402_validation_report.json` | -2.2781 | (raw z-score) | same | **YES** |
| `20260707_212833_validation_report.json` | -2.2781 | (raw z-score) | same | **YES** |
| `rydc_validation_20260712_203846.json` | 1.47e-116 | 0.0 (PASS) | pre-fix DSR (numerical zero bug) | **YES** |
| `rydc_validation_20260712_205844.json` | 1.47e-116 | 0.0 (PASS) | same | **YES** |
| `rydc_validation_20260712_210056.json` | 1.47e-116 | 0.0 (PASS) | same | **YES** |
| `rydc_validation_20260712_220238.json` | 0.00165 | 0.95 (FAIL) | **POST-FIX** — real probability, correct threshold | **NO** — this one used the fixed formula |

**Action:** 4 of the RYDC files and all 5 of the 20260707 validation reports must be re-run against the fixed DSR formula and corrected WFE/PBO gates before any of their PASS/FAIL labels are trusted. Note that `rydc_validation_20260712_220238.json` already shows `overall: FAIL` (DSR=0.00165 < 0.95, p_value=0.97, wfa_oos_positive=0.6 < 0.7, min_trades=52 < 100), so the re-runs are most likely to confirm FAIL — but they MUST be re-run for the evidence chain to be coherent. The corrected_evaluation.json file should also be regenerated from the fixed evaluator.

### 6.4 Safety carve-out artefacts (B7 + B1)

Two new self-contained test scripts now exist for the safety carve-out. Neither contacts a live broker, neither sends an order — both run entirely against temp files in a `kill_switch_recovery_*` / `alert_routing_*` prefix and clean themselves up by default.

| Script | What it covers |
|---|---|
| `scripts/test_kill_switch_recovery.py` | Six scenarios verifying `risk/kill_switch.py` fails CLOSED on every form of state corruption: (1) state file missing → INACTIVE (no spurious halt on first run); (2) corrupt JSON → ACTIVE + quarantined to `.corrupt.<ts>.json`; (3) unknown state value (e.g. `"BANANAS"`) → ACTIVE; (4) read-only state file on `activate()` → raises, never silent; (5) legacy state with missing keys → loads without KeyError, INACTIVE/ACTIVE preserved; (6) round-trip then mid-flight truncation → next load is ACTIVE (fail-closed). |
| `scripts/test_alert_routing.py` | Seven scenarios verifying `monitoring/alerts.py` never silently drops P0/P1/P2/P3 alerts: (1) P0 with no Telegram config → logged + in `alert_history`; (2) P1 same path; (3) P0 with mock Telegram → engine.send_alert called, severity mapped to CRITICAL, title and body preserved; (4) P2/P3 also route (mapped to WARNING/INFO); (5) engine exception → logged as `alert_dispatch_failed`, not propagated to caller; (6) `notify_kill_switch()` path produces a P0 that reaches the engine; (7) `AlertEngine.register_callback` is invoked (third delivery path). |

Both scripts are self-contained: `python scripts/test_kill_switch_recovery.py` and `python scripts/test_alert_routing.py`. They use only stdlib + already-imported project modules (`risk.kill_switch`, `monitoring.alerts`, `monitoring.alerting`, `core.enums`). No new dependencies. Pass/fail summary printed at end; non-zero exit code on any failure so they can be wired into a CI gate later.

### 6.5 What remains (NOT in Phase 1)

- **A1 — Real Spread Measurement** — still requires 7 full calendar days of live tick capture across Asian/London/NY/rollover sessions, with per-session mean/median/p90/max in bps plus separate commission and slippage components. XAUUSD/XPDUSD/XPTUSD in scope.
- **A2 — re-run with real costs** — blocked on A1.
- **A5 — multiple testing correction** — blocked on A2 (the correction depends on the actual family size once A2's outputs are in).
- **Re-runs of the 9 stale validation reports** documented in 6.3.
- **B2–B6, C, D, E, G** — explicitly paused per Section 1 until A1–A6 result is known. B1 + B7 (this section) are the only exceptions because they are paper-trading-process safety, not "go-live" gates.

### 6.6 What this section does NOT change

- The stopping rule (`reports/stopping_rule_2026_07_12.md`) is locked and was not modified.
- The sacred holdout (`data/sacred_holdout/holdout.csv`) was not touched.
- The "best strategy" question in Section 4 is still unanswerable — nothing in Phase 1 changes that.
