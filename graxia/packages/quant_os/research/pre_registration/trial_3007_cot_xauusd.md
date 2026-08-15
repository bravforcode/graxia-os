# Pre-Registration — Trial 3007: COT Managed-Money Contrarian on XAUUSD (Direction J)

**Status:** FROZEN — 2026-08-06 (params locked; no tuning after this point)
**Direction J** (`reports/stopping_rule_2026_08_06_direction_j.md`, ledger `research/trial_ledger_j.json`)

## Hypothesis

Extreme Managed-Money net positioning (z >= 2.0) on gold futures precedes
mean reversion in spot XAUUSD over 1-4 weeks. CFTC COT disaggregated data
(2021-2026) is now available — this trial was previously UNTESTED (Path B
3007) for lack of data.

## Frozen parameters

- Strategy: `COTPositioningStrategy` (strategies/path_b_wrappers.py)
- lookback_weeks = 52, entry_z = 2.0, exit_z = 0.5, min_hold = 1, max_hold = 4
- Weekly COT merged on daily XAUUSD D1
- Cost: XAUUSD 0.65 bps rt (verified, commission=0)

## Gates

GO: pooled DK t > 2.0 & Sharpe > 0; MARGINAL: t > 1.5; REJECT: otherwise.
Min trades >= 30 (weekly signals are sparse by construction).

## Rationale

Positioning extremes are a classic contrarian signal in commodities
literature (managed money tends to be wrong at extremes). Gold has a
dedicated COT series in-repo for the first time.
