# Stopping Rule — Direction J (XAUUSD Positioning/Cross-Asset) — Pre-Registration

**Status:** LOCKED — 2026-08-06
**Direction:** J (new — follows H stopped §4.4)
**Rationale for opening:** Data that was previously missing is now available:
- CFTC COT disaggregated positioning for XAUUSD (2021-2026, data/cot/) — enables
  Trial 3007 (COT contrarian), previously UNTESTED for lack of data.
- DXY_D1.csv (2018-2026) — enables Trial 3003 (cross-asset momentum DXY lead-lag),
  previously UNTESTED.
Both mechanisms are economically motivated (positioning extremes → reversal;
USD direction leads gold) and XAUUSD costs are verified correct (0.65 bps rt,
commission=0 — unaffected by the cost-model fix).

## Trials

| Trial | Mechanism | Data | Status |
|-------|-----------|------|--------|
| 3007 | COT contrarian (Managed Money z-score extremes) | COT 2021-2026 + XAUUSD D1 | NEW pre-registration |
| 3003 | Cross-asset momentum (DXY lead-lag) | DXY 2018-2026 + XAUUSD D1 | NEW pre-registration |

## Budget & stopping conditions

- Budget: 10 new hypotheses (subset of Path B untested block)
- Trial range: 3007-3016
- Stop when any: 10 used, 3 months (2026-11-06), 40 research-hours, or
  3 consecutive fails at the same gate.
- Separate ledger: research/trial_ledger_j.json

## Preconditions

1. Trials pre-registered BEFORE backtest (F27) — done 2026-08-06.
2. Costs: XAUUSD FROM_TICKS 0.65 bps rt (verified — commission=0).
3. Sacred holdout stays LOCKED.
4. Registry entries via registry_schema.stamp_trial_entry() with provenance.
