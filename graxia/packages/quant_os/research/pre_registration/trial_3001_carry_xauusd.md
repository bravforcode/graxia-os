# Pre-Registration — Trial 3001: Carry on XAUUSD (Direction L)

**Status:** FROZEN — 2026-08-07 (params locked; no tuning after this point)
**Direction L** (`reports/stopping_rule_2026_08_07_direction_l.md`, ledger `research/trial_ledger_l.json`)

## Hypothesis

Gold pays no yield; when US real rates (DGS10) are high, holding gold
carries an opportunity cost → gold underperforms; when rates fall, gold
rallies. The carry signal (negative of US rate, since gold's "base rate" = 0)
predicts gold direction over subsequent weeks.

## Why now

DGS10/DGS2 data was missing since Trial 3001's registration (Path B) —
now available via FRED (2016-2026, 2,621 daily rows).

## Frozen parameters

- Strategy: `compute_carry_signal` (strategies/carry.py)
- base_rate = 0.0 (gold pays nothing), quote_rate = DGS10 (US 10Y)
- vol_target = 0.10 (default)
- XAUUSD D1 + DGS10 (2016-2026)
- Cost: XAUUSD 0.65 bps rt
- Min trades >= 50

## Gates

GO: pooled DK t > 2.0 & mean > 0; MARGINAL: t > 1.5; REJECT: otherwise.
