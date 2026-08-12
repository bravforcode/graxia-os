# PHASE 5 — FEATURE & SIGNAL AUDIT
*Per R1–R18. Tier 2.*

---

## 5.1 — Feature Inventory

Two distinct feature stacks (Phase 8 established they are not shared):

**A. Backtest stack** (`strategies/` + `backtest/engine.py` indicators):
| Feature | Code | Window | Tested? |
|---|---|---|---|
| EMA 9/20/50/200 | `engine.py:643-646` (pandas) / `:296-299` (numba) | 9–200 | partial |
| RSI 14 | `engine.py:649` / `:300` | 14 | partial |
| ATR 14 | `engine.py:650` / `:301` | 14 | partial |
| Bollinger 20/2 | `engine.py:653-657` | 20 | `[unverified]` |
| ADX 14 | `engine.py:663-665` | 14 | `[unverified]` |
| Volume SMA 20 | `engine.py:660` | 20 | `[unverified]` |

**B. Live stack** (`regime/` + `scripts/build_features.py`): session/regime/microstructure/cross-asset families. `[build_features.py:8-14 documents ~5 families]`. **`[Best |r|/IC not reported in any artifact found]`.**

## 5.2 — IC / Correlation Verification

- **Claimed max |r| / IC**: `[NOT FOUND]` — no IC figure reported in `reports/`, `SUMMARY.md`, or `results/`. `SUMMARY.md:12` cites "58.2% accuracy OOS at conf≥0.75" — that is *accuracy*, not IC.
- Pearson vs Spearman: `[UNSPECIFIED]`.
- In-sample vs OOS IC: `[no IC reported]`.
- IC decay curve: `[ABSENT]`.
- ICIR: `[ABSENT]`.

## 5.3 — Multiple Testing Problem — CRITICAL

1. Total features tested across all sessions: **unknowable** — no hypothesis log (Phase 17.1). `scripts/build_features.py` alone defines ≥5 feature families × many sub-features. Estimate: **dozens to low-hundreds of feature variants tried**.
2. Independent hypotheses: `[unknowable without log]`.
3. α used: `[unstated; presumably 0.05]`.
4. E[false positives] = α × N_tests → if N=100, E[FP]=5; if N=500, E[FP]=25.
5. Bonferroni: `[NOT APPLIED anywhere found]`.
6. Benjamini-Hochberg FDR: `[NOT APPLIED]`.
7. → **Every "significant" feature finding must be labeled `[UNCORRECTED FOR MULTIPLE TESTING — may be spurious]`.** `SUMMARY.md:25` claims "confirmed Bonferroni+WF in feature diagnostic" but provides no corrected p-value and R5 says self-reports aren't evidence. `[UNVERIFIED]`.

## 5.4 — Feature Stationarity
`[ADF/KPSS not found as a reported result]`. Returns stationary (assumed); raw price as feature `[unverified]`. → P2.

## 5.5 — Feature Interdependence
`core/correlation.py`, `risk/correlation_provider.py` exist → capability present. Correlation matrix reported `[no]`. → P2.

## 5.6–5.9 — Regime breakdown, hypothesis log, importance stability, crowding
All `[ABSENT or UNVERIFIED]`. Hypothesis log is the foundational gap (Phase 17.1).

---

## Phase 5 — Verdict

**STATUS: INSUFFICIENT EVIDENCE.** No IC reported, no multiple-testing correction applied, no hypothesis log. The "58.2% accuracy" in `SUMMARY.md` is a single uncorrected point estimate on 67 trades. Per protocol 5.3, it must be labeled `[UNCORRECTED FOR MULTIPLE TESTING — may be spurious]`.
