# Pre-Registration — Trial 3003: DXY Lead-Lag Cross-Asset Momentum on XAUUSD (Direction J)

**Status:** FROZEN — 2026-08-06 (params locked; no tuning after this point)
**Direction J** (`reports/stopping_rule_2026_08_06_direction_j.md`, ledger `research/trial_ledger_j.json`)

## Hypothesis

DXY directional extremes lead gold moves (inverse USD-gold correlation).
Entering on DXY 60-day momentum z-score >= 1.0 (trading gold against the USD
move) with a 5-day hold captures the lead-lag between the dollar and gold.

## Frozen parameters

- Strategy: `CrossAssetMomentumStrategy` (strategies/path_b_wrappers.py)
- window = 60, z_threshold = 1.0, hold_days = 5
- DXY D1 (2018-2026) merged on XAUUSD D1
- Cost: XAUUSD 0.65 bps rt (verified, commission=0)

## Gates

GO: pooled DK t > 2.0 & Sharpe > 0; MARGINAL: t > 1.5; REJECT: otherwise.
Min trades >= 30.

## Rationale

Gold's strongest documented cross-asset relationship is its negative
correlation with the US dollar. If the relationship is lead-lag (USD moves
first), DXY extremes provide an entry timing signal for gold.
