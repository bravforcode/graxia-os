# Pre-Registration — Trial 4007: Cross-Asset Volatility Rank on BTCUSD (Direction K)

**Status:** RESOLVED — REJECTED 2026-08-06 (dk_t=-2.76, 5082 trades — Direction K STOPPED)
**Direction K** (`reports/stopping_rule_2026_08_06_direction_k.md`, ledger `research/trial_ledger_k.json`)

## Hypothesis

Volatility rank (realized vol percentile over 60-bar window) is mean-reverting:
entering when BTCUSD vol rank is low (< 20th pct) and holding while it expands
captures the vol-risk-premium / vol-clustering structure. Vol is the
tradeable quantity — structurally different from price-direction and
spread mechanisms (4005/4006 falsified).

## Frozen parameters

- Strategy: `compute_cvr_signals` (strategies/cross_asset_vol_rank.py)
- vol_window = 20, rank_window = 60, entry_low = 20.0, entry_high = 80.0
  (all defaults — pre-registered Trial 2008 config)
- BTCUSD_H1 (50k bars, 2020-2026)
- Cost: Binance taker 10 bps rt + 4 bps slippage = 14 bps rt
- Min trades >= 100

## Gates

GO: pooled DK t > 2.0 & mean > 0; MARGINAL: t > 1.5; REJECT: otherwise.
