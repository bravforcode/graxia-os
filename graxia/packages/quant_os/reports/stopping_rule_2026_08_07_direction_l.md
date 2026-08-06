# Stopping Rule — Direction L (Gold Vol Risk Premium) — Pre-Registration

**Status:** LOCKED — 2026-08-07
**Rationale for opening:** GVZ (Gold VIX) data was missing since Trial 1014's
registration — now available via FRED (GVZCLS, 2016-2026, 2,637 daily rows).
The volatility risk premium (implied GVZ > realized vol) is a well-documented
gold anomaly. This is a NEW direction because the mechanism (vol selling /
VRP harvesting) is structurally different from all tested price-directional
and cross-asset mechanisms (A-K all failed).

## Trial

| Trial | Mechanism | Data | Cost |
|-------|-----------|------|------|
| 4008 | Gold VRP (implied-realized spread z-score) | GVZCLS + XAUUSD D1 | XAUUSD 0.65 bps rt |

## Budget & stopping

- Budget: 6 trials, range 4008-4013
- Stop when any: 6 used, 3 months (2026-11-07), 30 research-hours,
  3 consecutive fails at same gate
- Ledger: research/trial_ledger_l.json

## Preconditions

1. Pre-registration BEFORE backtest (F27) — done 2026-08-07.
2. Registry via registry_schema.stamp_trial_entry() with provenance.
3. Sacred holdout stays LOCKED.
