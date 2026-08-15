# Pre-Registration — Trial 3008: COT Managed-Money Contrarian z>=1.5 (Direction J)

**Status:** FROZEN — 2026-08-06 (params locked; no tuning after this point)
**Direction J** (`reports/stopping_rule_2026_08_06_direction_j.md`, ledger `research/trial_ledger_j.json`)

## Background

Trial 3007 (z>=2.0) produced only **3 trades** in 5 years — the 2-sigma
threshold is too strict for the data window (14 extreme weeks, only 3 clean
entry crossings after position-holding logic). z>=1.5 yields **58 extreme
weeks** (~4x more signal). This is a NEW pre-registered threshold, not a
tuning of 3007 (3007 verdict INCONCLUSIVE stands).

## Hypothesis

Managed-Money net positioning z-score >= 1.5 (absolute) on gold futures
precedes mean reversion in XAUUSD over 1-4 weeks. Looser threshold provides
a powered sample while still targeting positioning extremes.

## Frozen parameters

- Strategy: COT contrarian (path_b_wrappers COTPositioningStrategy logic)
- lookback_weeks = 52, **entry_z = 1.5** (was 2.0), exit_z = 0.5,
  min_hold = 1, max_hold = 4
- Weekly COT on daily XAUUSD D1; cost 0.65 bps rt
- Min trades gate: >= 30

## Gates

GO: pooled DK t > 2.0 & mean > 0; MARGINAL: t > 1.5; REJECT: otherwise.
