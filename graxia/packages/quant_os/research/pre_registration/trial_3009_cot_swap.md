# Pre-Registration — Trial 3009: COT Swap-Dealer Contrarian z>=1.5 (Direction J)

**Status:** FROZEN — 2026-08-06 (params locked; no tuning after this point)
**Direction J** (`reports/stopping_rule_2026_08_06_direction_j.md`, ledger `research/trial_ledger_j.json`)

## Hypothesis

Swap-dealer net positioning z-score >= 1.5 (absolute) precedes mean reversion
in XAUUSD. Swap dealers are the counterparty to speculative flows — their
positioning extremes historically mark liquidity-driven turning points.
Different cohort than 3007/3008 (managed money) — tests whether the "smart
money" side carries the contrarian signal instead.

## Frozen parameters

- Strategy: COT contrarian on **Swap_Positions** cohort
- lookback_weeks = 52, entry_z = 1.5, exit_z = 0.5, min_hold = 1, max_hold = 4
- Weekly COT on daily XAUUSD D1; cost 0.65 bps rt
- Min trades gate: >= 30 (z>=1.5 swap events: 64 in window)

## Gates

GO: pooled DK t > 2.0 & mean > 0; MARGINAL: t > 1.5; REJECT: otherwise.
