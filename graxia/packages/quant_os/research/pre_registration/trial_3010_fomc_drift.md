# Pre-Registration — Trial 3010: FOMC Drift on XAUUSD (Direction J)

**Status:** RESOLVED — REJECTED 2026-08-06 (dk_t=-10.1, 43 events — hypothesis falsified)
**Direction J** (`reports/stopping_rule_2026_08_06_direction_j.md`, ledger `research/trial_ledger_j.json`)

## Hypothesis

Post-FOMC-announcement directional drift on XAUUSD: if the FOMC-day return is
in [0.2%, 3.0%], entering in the drift direction at next-bar open and holding
3 days captures post-announcement persistence. Event-based (~8 meetings/year
x 6y = ~40+ events) — higher frequency than weekly COT.

## Frozen parameters

- Strategy: `compute_fomc_drift_signals` (strategies/fomc_drift.py)
- FOMC_DATES built-in (57 dates, 2020-01-29 → 2026-12-16)
- drift_window_days = 3, min_fomc_return = 0.002, max_fomc_return = 0.03,
  atr_period = 14, stop_atr = 2.0 (all defaults — pre-registered)
- XAUUSD D1 (5623 bars); cost 0.65 bps rt
- Min trades gate: >= 25 (event-based — slightly relaxed vs 30 given ~40 max events)

## Gates

GO: pooled DK t > 2.0 & mean > 0; MARGINAL: t > 1.5; REJECT: otherwise.
