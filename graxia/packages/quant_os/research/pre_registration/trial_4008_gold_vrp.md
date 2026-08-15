# Pre-Registration — Trial 4008: Gold Volatility Risk Premium (Direction L)

**Status:** FROZEN — 2026-08-07 (params locked; no tuning after this point)
**Direction L** (`reports/stopping_rule_2026_08_07_direction_l.md`, ledger `research/trial_ledger_l.json`)

## Hypothesis

The gold volatility risk premium (GVZ implied vol minus realized vol) is
positive on average and mean-reverting: when VRP z-score >= 1.5 (implied
volatility rich), gold vol mean-reverts down over the following weeks.
Selling vol / fading VRP extremes captures the premium.

## Why this direction

- **Data unlocked**: GVZCLS (Gold VIX) 2016-2026 from FRED — missing since
  Trial 1014 registration
- **Structurally different**: vol-selling, not price-directional (A-K failed)
- **Documented anomaly**: options buyers overpay tail-risk protection

## Frozen parameters

- Strategy: `compute_vol_risk_premium_signals` (strategies/vol_risk_premium.py)
- vrp_lookback = 20, entry_z = 1.5, exit_z = 0.5, realized_vol_window = 20,
  gvz_smoothing = 5, regime_threshold = 0.0 (all defaults — Trial 1014 config)
- XAUUSD D1 + GVZCLS (2016-2026)
- Cost: XAUUSD 0.65 bps rt (verified, commission=0)
- Min trades >= 50

## Gates

GO: pooled DK t > 2.0 & mean > 0; MARGINAL: t > 1.5; REJECT: otherwise.
