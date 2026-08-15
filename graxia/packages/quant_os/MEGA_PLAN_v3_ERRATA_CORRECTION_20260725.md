# MEGA PLAN v3 Errata — Correction to Erratum 2 (Annualization "Bug")

**Date:** 2026-07-25 | **Corrects:** `MEGA_PLAN_v3_ERRATA_20260722.md`, Erratum 2 only
**Basis:** Empirical verification (timestamp spacing + per-bar vs daily-aggregated Sharpe invariance test), 3 symbols
**Status:** Erratum 2's mechanism and magnitude are unsupported. Its recommended fix is itself a regression. Do not apply it.

---

## What Erratum 2 claimed

> `backtest_suite.py:127` annualizes with `sqrt(252*96)` — "a factor meant for 15-minute intraday bars — applied to daily data." Cross-check: Phase 9's BTCUSD "Real backtest Sharpe" (2.84) / "Label-shuffle Sharpe" (0.2897) = 9.80 = √96, offered as "the signature of two return series run through two different annualization factors."
> **Action:** Fix to `sqrt(252)` as a P2 reporting bug.

## What's actually true

**The data is genuinely 15-minute bars, not daily data mislabeled.** Checked `data/XAUUSD_M15.csv` timestamp spacing directly: dominant gap is exactly `0:15:00` (49,433 of 50,000 diffs), with the remainder being weekend/session gaps. This is real M15 data. `sqrt(252*96)` is the textbook-correct annualization factor for 15-min bars on a ~24h market — it is not a daily-data bug.

**Per-bar and daily-aggregated Sharpe agree, ruling out an overlap/autocorrelation-driven inflation too.** Ran the actual `backtest_momentum` logic from `backtest_suite.py` on real data and compared two computations of the same underlying return stream:

| Symbol | Per-bar Sharpe (`sqrt(252·96)`, current code) | Daily-aggregated Sharpe (`sqrt(252)`) | Ratio |
|---|---|---|---|
| XAUUSD (24h) | 0.943 | 0.965 | 0.98 |
| US30 (M15 data, median 92 bars/day — near-continuous CFD quoting, not RTH-only) | -0.654 | -0.587 | 1.11 |
| NAS100 (same) | 0.943 | 0.856 | 1.10 |

If the current code were wrong by a factor of √96 (≈9.8×), these ratios would cluster near 9.8, not 1.0. They don't. `hold=5` in `backtest_momentum` is also a dead parameter (never referenced in the function body), so there's no held-position serial correlation to inflate the per-bar estimate either way.

**The errata's cross-check compared a real Sharpe to a label-shuffle (null-permutation) Sharpe.** A label-shuffle result is a null control — expected to sit near 0 by construction, regardless of annualization factor. A ratio of a real number over a near-zero null-control number landing near √96 is not evidence the two numbers share an annualization mismatch; it's arithmetic on a small denominator. (Not independently reproduced here — the Phase 9 report generating 2.84/0.2897 wasn't relocated — so this is a methodological objection to the cross-check, not a disproof of it.)

## Consequence

**Do not apply Erratum 2's recommended fix.** Changing `backtest_suite.py:95` (current line; was :127 in the original errata) from `sqrt(252*96)` to `sqrt(252)` would deflate every M15-based Sharpe in that script by ~9.8× — a real regression introduced in the name of fixing a bug that isn't there.

**What Erratum 2 got right and should be kept:** `backtest_suite.py` is an informal/quick multi-strategy screen. It does not feed any formal DK-test, pooled-Sharpe, or label-shuffle verdict — those all run through `edge_search_all.py` on `_D1.csv` data with `sqrt(252)`, which is correct for daily bars. That separation is real and matters; nothing here changes it.

**Action:** No code change to `backtest_suite.py`. Erratum 2 should be marked "superseded — mechanism and magnitude unsupported by empirical test" rather than acted on as written.
