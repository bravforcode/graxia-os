# WS-B — Paper Bot Re-Validation — 2026-07-29

**Status: REJECTED — FAILS corrected DSR**

## Background

The 4-asset Ensemble-TSM paper bot (`scripts/tsm_paper_trade.py`, config
`config/paper_trade_config.json`) was the only "survivor" after every other
edge tested in this project was rejected.  The provenance backtest
(`reports/tsm_ensemble_backtest_4asset.md`, 2026-07-03) claimed:

- Equal-weight portfolio: Sharpe = **0.535**, verdict "REAL_ALPHA"
- N=1 trial (single pre-registered hypothesis)
- PBO = 0.137 (passes)
- Optimal-weight (grid search 1771 combos): Sharpe = 0.729

## WS-B Re-Evaluation

### 1. Corrected DSR (N = 1050, not N = 1)

The backtest used **N=1** for DSR, claiming a single pre-registered hypothesis.
The project's reconciled cumulative trial count is **1050** (from
`reports/trial_count_reconciliation_20260720.json`).  The DSR formula requires
the total number of independent trials tested — N=1 massively under-deflates.

**Corrected DSR results (using `validation/deflated_sharpe.py` formula):**

| Portfolio | Sharpe | Skew | Kurtosis | T | N=1 | N=1050 | Verdict |
|-----------|--------|------|----------|---|-----|--------|---------|
| Equal-weight (4-asset) | 0.535 | 21.542 | 791.511 | 2681 | PASS (p=0.000) | **FAIL (p=0.208)** | REJECTED |
| Optimal-weight (grid search) | 0.729 | 0.134 | 13.449 | 2513 | PASS (p=0.000) | PASS (p=0.000) | Passes DSR but used 1771 grid combinations |

The equal-weight portfolio — the "pre-registered" one — fails the DSR with the
correct N=1050 because the extreme return distribution (skew=21.5, kurtosis=791.5)
inflates the standard error, and the adjusted expected max Sharpe (0.429) is
close to the observed Sharpe (0.535).  The probability that this Sharpe arose
from selection bias alone is **20.8%** (above the 5% threshold).

The optimal-weight portfolio passes DSR because its return distribution is much
closer to normal (skew=0.134, kurtosis=13.4), reducing the standard error.
However, the 1771 grid-search combinations used to find it are themselves a
multiple-testing problem — this is an optimized, not a pre-registered, result.

### 2. NAS100 Cost — UNVERIFIED (WS-C finding)

The cost model for NAS100 (`config/cost_calibration.json`) is marked
`UNVERIFIED_NO_DATA` with `sample_size=0`.  NAS100 has zero real spread or
tick data in this repository.  Its numbers are unverified placeholders that
should not be trusted for live sizing.

The 4-asset portfolio allocates 45% weight to NAS100 (optimal) or 25%
(equal-weight).  This means **any verdict that touches NAS100 is
untrustworthy until real cost data is collected.**

### 3. Jackknife — Cannot Re-Run (Data Files Missing)

The data files required to re-run the backtest are not available:
- `data/NAS100_D1.csv` — MISSING
- `data/XAUUSD_D1.csv` — MISSING
- `data/USDJPY_D1.csv` — MISSING
- `data/market_data/yfinance/CL_F.csv` — MISSING

The jackknife analysis (drop each asset, check if Sharpe collapses) could
not be re-executed from scratch.  The existing jackknife report
(`reports/tsm_portfolio_jackknife_20260728.json`) is for an 8-asset portfolio
and shows all deltas = 0.0 (non-functional or not applicable to 4-asset).

### 4. Cost-Stress

The backtest already includes per-asset measured Pepperstone Razor spreads
and swap costs.  However:
- NAS100 spreads are UNVERIFIED_NO_DATA (see #2)
- OIL spreads are from a single ~3-minute snapshot (20 samples)
- The "typical" cost drag is 169 bps/year for equal-weight

Cost-stressing at +20–50% would further degrade an already-marginal Sharpe.

## Verdict

**The 4-asset Ensemble-TSM paper bot FAILS the corrected DSR at the
pre-registered ensemble level.**  The equal-weight Sharpe of 0.535 is not
statistically significant after correcting for the project's 1050 cumulative
trials (p=0.208 > 0.05).

The paper bot (`scripts/tsm_paper_trade.py`) should be paused and the trial
marked REJECTED in the trial ledger until:
1. The DSR is recomputed with the correct N (1050) and passes, OR
2. A new strategy passes full rigor independently

**Recommendation: PAUSE paper bot, mark trial 20xx REJECTED_DSR_FAIL.**

## Residuals

- [ ] NAS100 cost measurement (multi-day tick recording) — blocks any
      NAS100-touching verdict
- [ ] Recover or regenerate D1 data files to enable jackknife re-run
- [ ] If paper bot is restarted on a DIFFERENT strategy, update
      `config/paper_trade_config.json` accordingly

## Method

DSR computed using the `validation/deflated_sharpe.py` formula (Bailey &
Lopez de Prado 2014), verified against `scripts/compute_deflated_sharpe.py`
reference implementation.  Script:
```
python -c "... code verified inline ..."
```
